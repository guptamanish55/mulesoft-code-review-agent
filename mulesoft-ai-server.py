#!/usr/bin/env python3
"""
Mule Guardian Server
Flask web server for the Mule Guardian Code Review Agent
"""

import os
import json
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
from werkzeug.utils import secure_filename

import xml.dom.minidom
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, tostring
import re
from mulesoft_ai_code_review_agent import MuleSoftCodeReviewAgent
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Import our AI agent
from mulesoft_ai_code_review_agent import MuleSoftCodeReviewAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xml', 'zip', 'jar'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def calculate_compliance_percentage(report):
    """Calculate compliance percentage based on violations and files scanned"""
    try:
        total_files = report.files_scanned
        total_violations = report.total_violations
        
        if total_files == 0:
            return 0.0
        
        # Calculate files with violations
        files_with_violations = set()
        for violation in report.violations:
            files_with_violations.add(violation.file_path)
        
        files_with_violations_count = len(files_with_violations)
        clean_files = total_files - files_with_violations_count
        
        # Base compliance on clean files percentage
        file_based_compliance = (clean_files / total_files) * 100
        
        # Apply severity weighting to adjust compliance - Fixed calculation
        priority_weights = {'HIGH': 10, 'MEDIUM': 5, 'LOW': 2, 'INFO': 1}
        total_severity_score = 0
        
        for priority, count in report.violations_by_priority.items():
            weight = priority_weights.get(priority, 1)
            total_severity_score += count * weight
        
        # Use a more reasonable max score calculation based on violations per file
        # Instead of assuming max violations per file, use actual violation distribution
        avg_violations_per_file = total_violations / max(files_with_violations_count, 1)
        max_possible_score = total_files * avg_violations_per_file * 10  # Max weight is 10 for HIGH
        
        # Calculate severity-adjusted compliance
        if max_possible_score > 0:
            severity_penalty = min(100, (total_severity_score / max_possible_score) * 100)
            severity_adjusted_compliance = max(0, 100 - severity_penalty)
        else:
            severity_adjusted_compliance = 100
        
        # Combine both metrics (70% file-based, 30% severity-based)
        final_compliance = (file_based_compliance * 0.7) + (severity_adjusted_compliance * 0.3)
        
        return round(final_compliance, 2)
        
    except Exception as e:
        logger.error(f"Error calculating compliance percentage: {e}")
        return 0.0

def get_compliance_score(compliance_percentage):
    """Get compliance score and status based on percentage"""
    if compliance_percentage >= 90:
        return {'status': 'Excellent', 'color': 'green', 'icon': '✅'}
    elif compliance_percentage >= 80:
        return {'status': 'Good', 'color': 'lightgreen', 'icon': '✓'}
    elif compliance_percentage >= 70:
        return {'status': 'Fair', 'color': 'orange', 'icon': '⚠️'}
    elif compliance_percentage >= 60:
        return {'status': 'Poor', 'color': 'darkorange', 'icon': '⚠️'}
    else:
        return {'status': 'Critical', 'color': 'red', 'icon': '❌'}

def get_compliance_recommendations(compliance_percentage, violations_by_priority):
    """Get recommendations based on compliance score"""
    recommendations = []
    
    if compliance_percentage < 70:
        recommendations.append("🔴 Critical: Immediate attention required to improve code quality")
        
    if violations_by_priority.get('HIGH', 0) > 0:
        recommendations.append(f"🚨 Fix {violations_by_priority['HIGH']} high-priority violations first")
        
    if violations_by_priority.get('MEDIUM', 0) > 5:
        recommendations.append(f"⚡ Address {violations_by_priority['MEDIUM']} medium-priority violations")
        
    if compliance_percentage >= 90:
        recommendations.append("🎉 Excellent compliance! Keep up the good work")
    elif compliance_percentage >= 80:
        recommendations.append("👍 Good compliance level. Focus on remaining issues")
    else:
        recommendations.append("📋 Consider implementing a code review process")
        
    return recommendations

def allowed_file(filename, allowed_extensions):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def extract_project_archive(archive_path, extract_to):
    """Extract project archive (ZIP/JAR) to directory"""
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True
    except Exception as e:
        logger.error(f"Failed to extract archive: {e}")
        return False

@app.route('/')
def index():
    """Serve the main HTML interface"""
    html_path = Path(__file__).parent / 'mulesoft-ai-review-ui.html'
    if html_path.exists():
        return send_file(html_path)
    else:
        return "MuleSoft AI Review UI not found", 404

@app.route('/test')
def test_page():
    """Serve the test page for checklist upload"""
    test_path = Path(__file__).parent / 'test_checklist_upload.html'
    if test_path.exists():
        return send_file(test_path)
    else:
        return "Test page not found", 404

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/upload-ruleset', methods=['POST'])
def upload_ruleset():
    """Upload PMD ruleset file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename, {'xml'}):
            return jsonify({'error': 'Invalid file type. Only XML files are allowed.'}), 400
        
        # Save ruleset file
        filename = secure_filename(file.filename) if file.filename else "ruleset.xml"
        ruleset_path = os.path.join(app.config['UPLOAD_FOLDER'], f"ruleset_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
        file.save(ruleset_path)
        
        return jsonify({
            'success': True,
            'ruleset_path': ruleset_path,
            'filename': filename
        })
    
    except Exception as e:
        logger.error(f"Error uploading ruleset: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-project', methods=['POST'])
def upload_project():
    """Upload MuleSoft project (directory or archive)"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        # Create temporary directory for project
        project_dir = tempfile.mkdtemp(prefix='mulesoft_project_')
        
        # Check if it's an archive file
        first_file = files[0]
        if allowed_file(first_file.filename, {'zip', 'jar'}):
            # Save and extract archive
            filename = secure_filename(first_file.filename) if first_file.filename else "project.zip"
            archive_path = os.path.join(project_dir, filename)
            first_file.save(archive_path)
            
            if not extract_project_archive(archive_path, project_dir):
                shutil.rmtree(project_dir)
                return jsonify({'error': 'Failed to extract project archive'}), 500
            
            # Clean up archive file
            os.remove(archive_path)
        else:
            # Handle directory upload
            for file in files:
                if file.filename:
                    # Create directory structure
                    file_path = os.path.join(project_dir, file.filename)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    file.save(file_path)
        
        return jsonify({
            'success': True,
            'project_path': project_dir,
            'file_count': len(files)
        })
    
    except Exception as e:
        logger.error(f"Error uploading project: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/run-review', methods=['POST'])
def run_code_review():
    """Run code review analysis"""
    try:
        data = request.get_json()
        ruleset_path = data.get('ruleset_path')
        project_path = data.get('project_path')
        analysis_mode = data.get('analysis_mode', 'comprehensive')
        priority_filter = data.get('priority_filter', 'all')
        report_format = data.get('report_format', 'html')
        
        if not ruleset_path or not project_path:
            return jsonify({'error': 'Missing ruleset_path or project_path'}), 400
        
        # Validate paths exist
        if not os.path.exists(ruleset_path):
            return jsonify({'error': 'Ruleset file not found'}), 404
        
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project directory not found'}), 404
        
        # Create AI agent and run review
        agent = MuleSoftCodeReviewAgent(project_path, ruleset_path)
        
        # Generate output path for report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"report_{timestamp}.json")
        
        # Apply analysis mode and priority filter
        logger.info(f"Running analysis with mode: {analysis_mode}, priority filter: {priority_filter}, report format: {report_format}")
        
        # Run the review with advanced options
        report = agent.run_review(output_path, analysis_mode=analysis_mode, priority_filter=priority_filter)
        
        # Calculate compliance percentage
        compliance_percentage = calculate_compliance_percentage(report)
        compliance_score = get_compliance_score(compliance_percentage)
        
        # Convert report to JSON-serializable format
        report_dict = {
            'project_name': report.project_name,
            'project_path': report.project_path,
            'ruleset_path': report.ruleset_path,
            'scan_timestamp': report.scan_timestamp,
            'total_violations': report.total_violations,
            'violations_by_priority': report.violations_by_priority,
            'violations_by_category': report.violations_by_category,
            'scan_duration': report.scan_duration,
            'files_scanned': report.files_scanned,
            'excluded_files': report.excluded_files,
            'summary': report.summary,
            'compliance_percentage': compliance_percentage,
            'compliance_score': compliance_score,
            'violations': []
        }
        
        # Convert violations
        for violation in report.violations:
            violation_dict = {
                'rule': violation.rule,
                'message': violation.message,
                'priority': violation.priority.name,
                'line': violation.line,
                'column': violation.column,
                'file_path': violation.file_path,
                'category': violation.category,
                'description': violation.description,
                'fix_suggestion': violation.fix_suggestion
            }
            report_dict['violations'].append(violation_dict)
        
        # Generate additional report formats based on user selection
        additional_files = {}
        
        if report_format == 'html':
            # Generate HTML report
            html_content = generate_html_report(report_dict)
            html_filename = f"mulesoft-report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            html_path = os.path.join(app.config['UPLOAD_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            additional_files['html_report'] = html_path
            additional_files['html_filename'] = html_filename
            
        elif report_format == 'pdf':
            # Generate PDF report using reportlab
            pdf_filename = f"mulesoft-report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
            
            # Generate proper PDF using reportlab
            generate_pdf_report(report_dict, pdf_path)
            
            additional_files['pdf_report'] = pdf_path
            additional_files['pdf_filename'] = pdf_filename
        
        # JSON format is always generated (default)
        if report_format == 'json':
            additional_files['json_report'] = output_path
            additional_files['json_filename'] = os.path.basename(output_path)
        
        return jsonify({
            'success': True,
            'report': report_dict,
            'report_file': output_path,
            'report_format': report_format,
            'additional_files': additional_files
        })
    
    except Exception as e:
        logger.error(f"Error running code review: {e}")
        error_message = str(e)
        
        # Provide more helpful error messages
        if "PMD is not installed" in error_message:
            error_message = "PMD is not installed. Please install PMD first."
        elif "PMD analysis failed" in error_message:
            error_message = "PMD analysis failed. Check the ruleset and project files."
        elif "Project path does not exist" in error_message:
            error_message = "Project path does not exist. Please check the uploaded files."
        
        return jsonify({
            'success': False,
            'error': error_message,
            'message': 'Failed to run code review',
            'details': str(e)
        }), 500

@app.route('/api/download-report/<filename>')
def download_report(filename):
    """Download generated report file"""
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'Report file not found'}), 404
    except Exception as e:
        logger.error(f"Error downloading report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-html', methods=['POST'])
def export_html_report():
    """Export report as HTML"""
    try:
        data = request.get_json()
        report = data.get('report')
        
        if not report:
            return jsonify({'error': 'No report data provided'}), 400
        
        # Ensure compliance data is included if not already present
        if 'compliance_percentage' not in report:
            # Calculate compliance percentage from the report data
            mock_report = type('MockReport', (), {
                'files_scanned': report.get('files_scanned', 0),
                'total_violations': report.get('total_violations', 0),
                'violations_by_priority': report.get('violations_by_priority', {}),
                'violations': [type('MockViolation', (), v)() for v in report.get('violations', [])]
            })()
            
            for i, v in enumerate(report.get('violations', [])):
                mock_violation = mock_report.violations[i]
                mock_violation.file_path = v.get('file_path', '')
            
            report['compliance_percentage'] = calculate_compliance_percentage(mock_report)
            report['compliance_score'] = get_compliance_score(report['compliance_percentage'])
        
        # Generate HTML report
        html_content = generate_html_report(report)
        
        # Save HTML file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_filename = f"mulesoft-report_{timestamp}.html"
        html_path = os.path.join(app.config['UPLOAD_FOLDER'], html_filename)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return jsonify({
            'success': True,
            'html_file': html_path,
            'filename': html_filename
        })
    
    except Exception as e:
        logger.error(f"Error exporting HTML report: {e}")
        return jsonify({'error': str(e)}), 500

def generate_html_report(report):
    """Generate HTML report content"""
    
    # Sort violations by priority (High to Low) in the backend
    priority_order = {'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'INFO': 4}
    sorted_violations = sorted(report['violations'], 
                             key=lambda x: priority_order.get(x['priority'], 5))
    
    # Create a copy of the report with sorted violations
    report_with_sorted_violations = report.copy()
    report_with_sorted_violations['violations'] = sorted_violations
    
    # Get compliance recommendations
    compliance_recommendations = get_compliance_recommendations(
        report.get('compliance_percentage', 0),
        report.get('violations_by_priority', {})
    )
    report_with_sorted_violations['compliance_recommendations'] = compliance_recommendations
    
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Mule Guardian Code Review Report - {{ report.project_name }}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }
        .summary-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .summary-card h3 {
            margin: 0 0 10px 0;
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .summary-card .number {
            font-size: 2.5em;
            font-weight: bold;
            color: #333;
        }
        .compliance-card {
            background: white;
            padding: 25px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
            border: 3px solid;
            grid-column: span 2;
        }
        .compliance-excellent { border-color: #28a745; }
        .compliance-good { border-color: #90ee90; }
        .compliance-fair { border-color: #ffa500; }
        .compliance-poor { border-color: #ff8c00; }
        .compliance-critical { border-color: #dc3545; }
        .compliance-score {
            font-size: 3.5em;
            font-weight: bold;
            margin: 10px 0;
        }
        .compliance-status {
            font-size: 1.4em;
            font-weight: bold;
            margin: 10px 0;
        }
        .compliance-icon {
            font-size: 2em;
            margin-bottom: 10px;
        }
        .recommendations {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }
        .recommendations h3 {
            color: #856404;
            margin-top: 0;
        }
        .recommendations ul {
            list-style: none;
            padding: 0;
        }
        .recommendations li {
            padding: 5px 0;
            color: #856404;
        }
        .content {
            padding: 30px;
        }
        .section {
            margin-bottom: 40px;
        }
        .section h2 {
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .violation {
            background: white;
            border: 1px solid #e1e5e9;
            border-radius: 8px;
            margin-bottom: 15px;
            overflow: hidden;
        }
        .violation-header {
            padding: 15px 20px;
            border-bottom: 1px solid #e1e5e9;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .violation-body {
            padding: 20px;
        }
        .priority-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .priority-high { background: #ff6b6b; color: white; }
        .priority-medium { background: #feca57; color: white; }
        .priority-low { background: #48dbfb; color: white; }
        .priority-info { background: #1dd1a1; color: white; }
        .rule-name {
            font-weight: bold;
            color: #333;
            font-size: 1.1em;
        }
        .category {
            color: #666;
            font-size: 0.9em;
        }
        .file-info {
            background: #f8f9fa;
            padding: 10px 15px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.9em;
            color: #333;
        }
        .message {
            margin: 15px 0;
            padding: 15px;
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 4px;
            color: #856404;
        }
        .fix-suggestion {
            margin-top: 15px;
            padding: 15px;
            background: #d1ecf1;
            border: 1px solid #bee5eb;
            border-radius: 4px;
            color: #0c5460;
        }
        .fix-suggestion strong {
            color: #0a4b53;
        }
        @media (max-width: 768px) {
            .summary-grid { grid-template-columns: repeat(2, 1fr); }
            .compliance-card { grid-column: span 2; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Mule Guardian Code Review Report</h1>
            <p>{{ report.project_name }} | Generated on {{ report.scan_timestamp[:10] }}</p>
        </div>
        
        <div class="summary-grid">
            <!-- Compliance Score Card -->
            <div class="compliance-card compliance-{{ report.compliance_score.status.lower() }}">
                <h3>Project Compliance Score</h3>
                <div class="compliance-icon">{{ report.compliance_score.icon }}</div>
                <div class="compliance-score" style="color: {{ report.compliance_score.color }};">{{ report.compliance_percentage }}%</div>
                <div class="compliance-status" style="color: {{ report.compliance_score.color }};">{{ report.compliance_score.status }}</div>
            </div>
            
            <div class="summary-card">
                <h3>Total Violations</h3>
                <div class="number">{{ report.total_violations }}</div>
            </div>
            <div class="summary-card">
                <h3>High Priority</h3>
                <div class="number">{{ report.violations_by_priority.get('HIGH', 0) }}</div>
            </div>
            <div class="summary-card">
                <h3>Files Scanned</h3>
                <div class="number">{{ report.files_scanned }}</div>
            </div>
            <div class="summary-card">
                <h3>Scan Duration</h3>
                <div class="number">{{ "%.2f"|format(report.scan_duration) }}s</div>
            </div>
        </div>
        
        <div class="content">
            <!-- Compliance Recommendations -->
            {% if report.compliance_recommendations %}
            <div class="recommendations">
                <h3>📋 Compliance Recommendations</h3>
                <ul>
                    {% for recommendation in report.compliance_recommendations %}
                    <li>{{ recommendation }}</li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}
            
            <div class="section">
                <h2>Analysis Summary</h2>
                <p style="font-size: 1.2em; color: #333;">{{ report.summary }}</p>
            </div>
            
            <div class="section">
                <h2>Detailed Violations (Sorted by Priority: High → Low)</h2>
                {% for violation in report.violations %}
                <div class="violation">
                    <div class="violation-header">
                        <div>
                            <div class="rule-name">{{ violation.rule }}</div>
                            <div class="category">{{ violation.category }}</div>
                        </div>
                        <span class="priority-badge priority-{{ violation.priority.lower() }}">
                            {{ violation.priority }}
                        </span>
                    </div>
                    <div class="violation-body">
                        <div class="file-info">
                            {{ violation.file_path }}:{{ violation.line }}:{{ violation.column }}
                        </div>
                        <div class="message">
                            <strong>Issue:</strong> {{ violation.message }}
                        </div>
                        {% if violation.fix_suggestion %}
                        <div class="fix-suggestion">
                            <strong>Fix Suggestion:</strong> {{ violation.fix_suggestion }}
                        </div>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
    """
    
    from jinja2 import Template
    template = Template(html_template)
    return template.render(report=report_with_sorted_violations)

# Comprehensive ruleset mapping - all rules from PMD files
COMPREHENSIVE_RULESET_MAPPING = {
    'APIKitConfigMustReferenceRAML': {
        'message': 'APIKit configuration must reference a RAML file',
        'description': 'Ensures APIKit configuration references a RAML specification.',
        'priority': 3,
        'xpath': '//*[local-name()=\'config\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/apikit\' and not(@raml)]'
    },
    'APIKitRouterMustBeConfigured': {
        'message': 'APIKit router must be properly configured with RAML specification',
        'description': 'Ensures APIKit router has proper RAML configuration.',
        'priority': 3,
        'xpath': '//*[local-name()=\'router\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/apikit\' and not(@config-ref)]'
    },
    'AllDependenciesAreMavenized': {
        'message': 'All dependencies should be managed via Maven - avoid manual JARs or non-mavenized libraries',
        'description': 'This rule checks that all dependencies are defined with groupId, artifactId, and version.',
        'priority': 3,
        'xpath': '//dependencies/dependency[not(groupId and artifactId and version)]'
    },
    'ApiSpecificationNaming': {
        'message': 'API specification files must follow naming convention: api-name-version.raml (e.g., customer-api-v1.raml)',
        'description': 'Ensures API specification files follow proper naming conventions.',
        'priority': 3,
        'xpath': '//*[@file and contains(@file, \'.raml\') and not(matches(@file, \'^[a-z]+(-[a-z0-9]+)*-v[0-9]+(\\.[0-9]+)*\\.raml$\'))]'
    },
    'AvoidComplexDataWeaveInTransform': {
        'message': 'Avoid overly complex DataWeave expressions in single transform - consider breaking into multiple steps',
        'description': 'Flags potentially complex DataWeave transformations.',
        'priority': 3,
        'xpath': '//*[local-name()=\'transform\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/ee/core\' and string-length(string-join(.//text(), \'\')) > 1000]'
    },
    'AvoidDebugInfoInProduction': {
        'message': 'Debug and info level logs should not contain sensitive information in production',
        'description': 'Prevents logging sensitive information at debug/info levels in production environments.',
        'priority': 3,
        'xpath': '//*[local-name()=\'logger\' and (@level=\'DEBUG\' or @level=\'INFO\') and (@message[contains(lower-case(.), \'password\')] or @message[contains(lower-case(.), \'token\')] or @message[contains(lower-case(.), \'secret\')] or @message[contains(lower-case(.), \'client_secret\')])]'
    },
    'AvoidDeepNestingInFlows': {
        'message': 'Avoid deep nesting in flows - consider using sub-flows for better maintainability',
        'description': 'Flags flows with excessive nesting depth.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow\' and count(.//*) > 50]'
    },
    'AvoidDuplicateProcessing': {
        'message': 'Duplicate processing should be avoided - use caching or deduplication mechanisms',
        'description': 'Flags potential duplicate processing scenarios that should be optimized.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow\' and count(.//*[local-name()=\'request\' and @url]) > 1]'
    },
    'AvoidEmptyFlows': {
        'message': 'Flows should not be empty - add processing logic or remove unused flows',
        'description': 'Ensures flows contain actual processing logic.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow\' and count(*) = 0]'
    },
    'AvoidEmptyTryScope': {
        'message': 'Try scope should not be empty - add actual processing logic',
        'description': 'Ensures try blocks contain actual processing logic.',
        'priority': 3,
        'xpath': '//*[local-name()=\'try\' and count(child::*) = 0]'
    },
    'AvoidEmptyVariable': {
        'message': 'Variables should not be empty - provide meaningful values',
        'description': 'Checks for empty variables.',
        'priority': 3,
        'xpath': '//*[local-name()=\'set-variable\' and (@value=\'\' or not(@value))]'
    },
    'AvoidGlobalConfiguration': {
        'message': 'Avoid global configuration - use specific configuration references',
        'description': 'Recommends using specific configuration references instead of global configurations.',
        'priority': 3,
        'xpath': '//*[local-name()=\'config\' and not(@name)]'
    },
    'AvoidHardcodedValues': {
        'message': 'Avoid hardcoded values - use properties or configuration files instead',
        'description': 'Flags potential hardcoded values that should be externalized.',
        'priority': 3,
        'xpath': '//*[@*[matches(., \'^[0-9]+$\') or matches(., \'^[a-zA-Z0-9]+://[^${]\')]]'
    },
    'AvoidJsonLoggerForJava17': {
        'message': 'Avoid using JsonLogger to ensure compatibility with Java 17 and prevent performance issues',
        'description': 'Recommend avoiding JsonLogger unless explicitly required and validated for performance and compatibility.',
        'priority': 3,
        'xpath': '//*[contains(@class, \'JsonLogger\')]'
    },
    'AvoidLargePayloadsInMemory': {
        'message': 'Large payloads should be streamed, not loaded entirely into memory',
        'description': 'Encourages streaming for large payloads to improve memory usage.',
        'priority': 3,
        'xpath': '//*[local-name()=\'set-payload\' and contains(@value, \'payload\') and not(contains(@value, \'stream\'))]'
    },
    'AvoidLoggingPayload': {
        'message': 'Payload must not be logged - use #[payload.^raw] or specific fields instead',
        'description': 'Check for logging payload using loggers in XML. Payload should not be logged directly for security reasons.',
        'priority': 3,
        'xpath': '//*[local-name() = \'logger\' and contains(@message, \'#[payload\') and not(contains(@message, \'#[payload.^raw]\'))]'
    },
    'AvoidNestedLoops': {
        'message': 'Avoid nested loops as they can cause performance issues - consider using DataWeave transformations',
        'description': 'Detects nested foreach loops that can impact performance.',
        'priority': 3,
        'xpath': '//*[local-name()=\'foreach\']//*[local-name()=\'foreach\']'
    },
    'AvoidSQLInjection': {
        'message': 'Use parameterized queries to prevent SQL injection attacks - avoid string concatenation in SQL',
        'description': 'Detects potential SQL injection vulnerabilities by checking for concatenated queries.',
        'priority': 3,
        'xpath': '//*[(local-name()=\'select\' or local-name()=\'insert\' or local-name()=\'update\' or local-name()=\'delete\') and namespace-uri()=\'http://www.mulesoft.org/schema/mule/db\' and contains(string(.), \'#[\') and contains(string(.), \'++\')]'
    },
    'AvoidSensitiveDataInLogs': {
        'message': 'Do not log sensitive data like tokens, passwords, or secrets - use #[payload.^raw] or specific fields',
        'description': 'Ensure no sensitive information is logged, such as tokens or passwords.',
        'priority': 3,
        'xpath': '//*[local-name()=\'logger\' and (@message[contains(lower-case(.), \'token\')] or @message[contains(lower-case(.), \'password\')] or @message[contains(lower-case(.), \'secret\')] or @message[contains(lower-case(.), \'client_secret\')])]'
    },
    'AvoidUnusedVariables': {
        'message': 'Ensure no unused variables, sub-flows exist',
        'description': 'Flags potentially unused variables and sub-flows that should be cleaned up.',
        'priority': 3,
        'xpath': '//*[local-name()=\'set-variable\' and @variableName and not(following::*[contains(@value, concat(\'#[vars.\', @variableName, \']\'))])]'
    },
    'CheckClientIdHeaders': {
        'message': 'Global HTTP Requester should include \'client_id\' and \'client_secret\' headers for authentication',
        'description': 'Ensures that \'client_id\' and \'client_secret\' are set in HTTP listener config headers.',
        'priority': 3,
        'xpath': '//*[local-name()=\'request-connection\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/http\' and not(.//header[@name=\'client_id\'] and .//header[@name=\'client_secret\'])]'
    },
    'CommonGlobalErrorHandlerImplemented': {
        'message': 'A common global error handler must be implemented at project level',
        'description': 'Verify that a global error handler is present at project-level configuration.',
        'priority': 3,
        'xpath': '//*[local-name()=\'mule\' and not(.//*[local-name()=\'error-handler\'])]'
    },
    'CorrelationIdLogging': {
        'message': 'Log correlation ID to maintain E2E traceability across APIs',
        'description': 'Ensure correlation ID is included in logs to trace transactions across layers.',
        'priority': 3,
        'xpath': '//*[local-name()=\'logger\' and @message and not(contains(@message, \'correlationId\') or contains(@message, \'correlation-id\') or contains(@message, \'attributes.correlationId\') or contains(@message, \'correlation_id\'))]'
    },
    'DatabaseConnectionPoolConfiguration': {
        'message': 'Database connections must have proper connection pooling configuration (maxPoolSize, minPoolSize)',
        'description': 'Ensures database connections have proper pooling settings.',
        'priority': 3,
        'xpath': '//*[local-name()=\'config\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/db\' and not(@maxPoolSize and @minPoolSize)]'
    },
    'DisallowInsecureTLS': {
        'message': 'Do not use insecure=true for TLS communication - this disables certificate validation',
        'description': 'Flags any configuration that sets insecure=\"true\" in TLS communication, which disables certificate validation.',
        'priority': 3,
        'xpath': '//*[@insecure=\'true\']'
    },
    'DisallowPlaintextSensitiveAttributes': {
        'message': 'Sensitive values must use secure property placeholders (e.g., ${secure::...})',
        'description': 'Detects hardcoded sensitive values like username, password, clientId, and clientSecret not using secure property placeholders.',
        'priority': 3,
        'xpath': '//*[@username and not(starts-with(@username, \'${secure::\')) and not(starts-with(@username, \'${\'))] | //*[@password and not(starts-with(@password, \'${secure::\')) and not(starts-with(@password, \'${\'))] | //*[@clientId and not(starts-with(@clientId, \'${secure::\')) and not(starts-with(@clientId, \'${\'))] | //*[@clientSecret and not(starts-with(@clientSecret, \'${secure::\')) and not(starts-with(@clientSecret, \'${\'))] | //*[@secret and not(starts-with(@secret, \'${secure::\')) and not(starts-with(@secret, \'${\'))]'
    },
    'EnforceTLSInHttpConnections': {
        'message': 'HTTPS communication must be used - replace http:// with https://',
        'description': 'Ensure HTTP request and listener connections use HTTPS (TLS 1.2+).',
        'priority': 3,
        'xpath': '//*[local-name() = \'request\' and @url and contains(@url, \'http://\') and not(contains(@url, \'https://\'))] | //*[local-name() = \'listener\' and @config-ref and contains(@config-ref, \'http\') and not(contains(@config-ref, \'https\'))] | //*[local-name() = \'listener-connection\' and @protocol and contains(@protocol, \'http\') and not(contains(@protocol, \'https\'))] | //*[local-name() = \'request-connection\' and @protocol and contains(@protocol, \'http\') and not(contains(@protocol, \'https\'))]'
    },
    'EnvironmentSpecificPropertyFiles': {
        'message': 'Property files should be environment-specific (e.g., config-dev.yaml, config-prod.yaml)',
        'description': 'Avoid using general-purpose property files without environment-specific overrides.',
        'priority': 3,
        'xpath': '//*[@file and contains(@file, \'application.properties\') and not(contains(@file, \'-dev.properties\') or contains(@file, \'-prod.properties\') or contains(@file, \'-test.properties\') or contains(@file, \'-qa.properties\'))] | //*[@file and contains(@file, \'config.yaml\') and not(contains(@file, \'-dev.yaml\') or contains(@file, \'-prod.yaml\') or contains(@file, \'-test.yaml\') or contains(@file, \'-qa.yaml\'))]'
    },
    'ErrorHandlerExists': {
        'message': 'Error handlers should be defined for critical operations',
        'description': 'Ensures error handling is properly implemented. Excludes flows that reference global error handlers or have global error handler configurations.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow\' and not(*[local-name()=\'error-handler\']) and not(*[local-name()=\'error-handler\'][@ref]) and not(*[local-name()=\'error-handler\'][@ref=\'global-error-handler\']) and not(*[local-name()=\'try\']) and not(*[local-name()=\'catch-exception-strategy\']) and not(*[local-name()=\'exception-strategy\']) and not(*[local-name()=\'exception-strategy\'][@ref]) and not(*[local-name()=\'on-error-continue\']) and not(*[local-name()=\'on-error-propagate\']) and not(ancestor::*[local-name()=\'mule\']//*[local-name()=\'error-handler\' and @name=\'global-error-handler\'])]'
    },
    'ErrorHandlerMustHaveOnErrorPropagate': {
        'message': 'Error handlers must include on-error-propagate for unhandled exceptions',
        'description': 'Ensures error handlers have proper exception propagation.',
        'priority': 3,
        'xpath': '//*[local-name()=\'error-handler\' and not(.//*[local-name()=\'on-error-propagate\'])]'
    },
    'FlowNameHyphenatedLowerCase': {
        'message': 'Flow names must be lowercase and hyphen-separated (e.g., process-customer-data)',
        'description': 'Ensures flow names adhere to lowercase-hyphenated pattern.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow\' and @name and not(matches(@name, \'^[a-z]+(-[a-z0-9]+)*$\'))]'
    },
    'FlowVariableNamingConvention': {
        'message': 'Flow variable names must be lower camel case and start with \'var\' prefix (e.g., varCustomerId)',
        'description': 'Enforces flow variables to start with \'var\' followed by UpperCamelCase naming.',
        'priority': 3,
        'xpath': '//*[local-name()=\'set-variable\' and @variableName and not(matches(@variableName, \'^var[A-Z][a-zA-Z0-9]*$\'))]'
    },
    'GroupIdMatchesBusinessGroupId': {
        'message': 'groupId must follow organizational standards (e.g., com.company.project)',
        'description': 'This rule checks that the groupId follows organizational standards.',
        'priority': 3,
        'xpath': '/project/groupId[not(matches(string(.), \'^[a-z]+\\.[a-z]+(\\.[a-z0-9]+)*$\'))]'
    },
    'HTTPRequestTimeoutConfiguration': {
        'message': 'HTTP requests must have proper timeout configuration',
        'description': 'Ensures HTTP requests have timeout settings for reliability.',
        'priority': 3,
        'xpath': '//*[local-name()=\'request-connection\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/http\' and not(@responseTimeout)]'
    },
    'LoggerVerbosityLevelForPayload': {
        'message': 'Logger verbosity level should be appropriate for payload logging',
        'description': 'Ensures appropriate logger levels for payload logging.',
        'priority': 3,
        'xpath': '//*[local-name()=\'logger\' and @level=\'INFO\' and contains(@message, \'#[payload\')]'
    },
    'MUnitTestMustHaveAssertions': {
        'message': 'MUnit tests must include assertions to validate behavior',
        'description': 'Ensures MUnit tests have proper assertions.',
        'priority': 3,
        'xpath': '//*[local-name()=\'test\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/core\' and not(.//*[local-name()=\'assert-that\'] or .//*[local-name()=\'assert-equals\'] or .//*[local-name()=\'assert-not-null\'])]'
    },
    'MocksMustBeClearedAfterTest': {
        'message': 'Mocks must be cleared after each test to prevent interference',
        'description': 'Ensures mocks are properly cleaned up after tests.',
        'priority': 3,
        'xpath': '//*[local-name()=\'mock\' and namespace-uri()=\'http://www.mulesoft.org/schema/mule/core\' and not(following::*[local-name()=\'clear\'])]'
    },
    'PreferSubFlowsOverFlowRef': {
        'message': 'Prefer sub-flows over flow-ref for better maintainability',
        'description': 'Recommends using sub-flows instead of flow-ref for better code organization.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow-ref\' and not(contains(@name, \'sub-\'))]'
    },
    'ProjectNameMatchesGitRepo': {
        'message': 'Project name should follow kebab-case naming convention (e.g., my-mulesoft-api)',
        'description': 'Ensures the name field in pom.xml matches naming conventions.',
        'priority': 3,
        'xpath': '//project/name[not(matches(string(.), \'^[a-z]+(-[a-z0-9]+)*$\'))]'
    },
    'ProjectPomMustHaveParent': {
        'message': 'The project POM must contain a parent element for proper Maven inheritance',
        'description': 'Checks if the root project element in a POM file has a child parent element.',
        'priority': 3,
        'xpath': '/project[not(parent)]'
    },
    'ProperExceptionHandling': {
        'message': 'Use specific exception types instead of generic Exception',
        'description': 'Encourages specific exception handling for better error management.',
        'priority': 3,
        'xpath': '//*[local-name()=\'catch-exception-strategy\' and @type=\'java.lang.Exception\']'
    },
    'PropertiesCamelCaseValidation': {
        'message': 'Properties must follow camelCase naming convention',
        'description': 'Ensures properties follow camelCase naming convention.',
        'priority': 3,
        'xpath': '//*[@key and not(matches(@key, \'^[a-z][a-zA-Z0-9]*$\'))]'
    },
    'PropertiesFileNameConvention': {
        'message': 'Properties file names must follow pattern: config-env.yaml (e.g., config-dev.yaml)',
        'description': 'Ensures properties files follow environment-specific naming conventions.',
        'priority': 3,
        'xpath': '//*[@file and contains(@file, \'config\') and not(matches(@file, \'config-(dev|prod|test|qa|stage|uat)\\.(yaml|yml|properties)$\'))]'
    },
    'RAMLApiSpecAsExchangeDependency': {
        'message': 'RAML API specification should be included as exchange dependency',
        'description': 'Ensures RAML specifications are properly included as dependencies.',
        'priority': 3,
        'xpath': '//*[local-name()=\'exchange\' and not(.//*[local-name()=\'raml\'])]'
    },
    'RequireAutoDiscovery': {
        'message': 'API Gateway autodiscovery must be configured for proper API management',
        'description': 'Ensures API Gateway autodiscovery is properly configured.',
        'priority': 3,
        'xpath': '//*[local-name()=\'mule\' and not(.//*[contains(local-name(), \'autodiscovery\')]) and not(.//*[local-name()=\'flow\' or local-name()=\'sub-flow\'])]'
    },
    'RequireCommonLibraries': {
        'message': 'Common libraries must be included for standard functionality',
        'description': 'Ensures common libraries are included for standard functionality.',
        'priority': 3,
        'xpath': '//*[local-name()=\'dependency\' and not(contains(@artifactId, \'common\'))]'
    },
    'RequireConfigurationProperties': {
        'message': 'Configuration properties must be properly defined',
        'description': 'Ensures configuration properties are properly defined.',
        'priority': 3,
        'xpath': '//*[local-name()=\'config\' and not(@file or @key)]'
    },
    'RequireDocumentationForFlows': {
        'message': 'Flows must have proper documentation',
        'description': 'Ensures flows have proper documentation.',
        'priority': 3,
        'xpath': '//*[local-name()=\'flow\' and not(.//*[local-name()=\'doc:description\'])]'
    },
    'RequireMonitoringConfiguration': {
        'message': 'Monitoring configuration must be properly set up',
        'description': 'Ensures monitoring configuration is properly set up.',
        'priority': 3,
        'xpath': '//*[local-name()=\'mule\' and not(.//*[local-name()=\'monitoring\'])]'
    },
    'RequireSecurityHeaders': {
        'message': 'Security headers must be properly configured',
        'description': 'Ensures security headers are properly configured.',
        'priority': 3,
        'xpath': '//*[local-name()=\'listener\' and not(.//header[@name=\'X-Frame-Options\'])]'
    },
    'RequireSecurityMechanisms': {
        'message': 'Security mechanisms must be properly implemented',
        'description': 'Ensures security mechanisms are properly implemented.',
        'priority': 3,
        'xpath': '//*[local-name()=\'mule\' and not(.//*[local-name()=\'security\'])]'
    },
    'TransactionStateLogging': {
        'message': 'Transaction state must be logged for debugging',
        'description': 'Ensures transaction state is logged for debugging purposes.',
        'priority': 3,
        'xpath': '//*[local-name()=\'logger\' and not(contains(@message, \'transaction\'))]'
    },
    'TryScopeNotEmpty': {
        'message': 'Try scope should not be empty - add actual processing logic',
        'description': 'Ensures try blocks contain actual processing logic.',
        'priority': 3,
        'xpath': '//*[local-name()=\'try\' and count(*) = 0]'
    },
    'UseConnectionPooling': {
        'message': 'Use connection pooling for database and HTTP connections',
        'description': 'Encourages the use of connection pooling for better performance.',
        'priority': 3,
        'xpath': '//*[local-name()=\'config\' and (namespace-uri()=\'http://www.mulesoft.org/schema/mule/db\' or namespace-uri()=\'http://www.mulesoft.org/schema/mule/http\') and not(@maxPoolSize)]'
    },
    'VersionAlignmentRule': {
        'message': 'Mule runtime version must be aligned with dependencies',
        'description': 'Ensures Mule runtime version is aligned with dependencies.',
        'priority': 3,
        'xpath': '//*[local-name()=\'mule\' and not(@version)]'
    },
    'WSDLAndXSDInCorrectFolder': {
        'message': 'WSDL and XSD files must be in the correct folder structure',
        'description': 'Ensures WSDL and XSD files are in the correct folder structure.',
        'priority': 3,
        'xpath': '//*[@file and (contains(@file, \'.wsdl\') or contains(@file, \'.xsd\')) and not(contains(@file, \'/src/main/resources/\'))]'
    }
}

def generate_xpath_from_rule(rule_name, rule_description):
    """Generate XPath expression by mapping to comprehensive ruleset rules"""
    desc_lower = rule_description.lower()
    name_lower = rule_name.lower()
    
    # Direct mapping based on rule name for exact matches
    if rule_name in COMPREHENSIVE_RULESET_MAPPING:
        return COMPREHENSIVE_RULESET_MAPPING[rule_name]['xpath']
    
    # Try to match checklist items to comprehensive ruleset rules by keywords
    for rule_key, rule_data in COMPREHENSIVE_RULESET_MAPPING.items():
        # Check if any keywords from the comprehensive rule match the description
        if any(keyword in desc_lower for keyword in rule_data['keywords']):
            return rule_data['xpath']
    
    # If no match found, try to match by rule name similarity
    for rule_key, rule_data in COMPREHENSIVE_RULESET_MAPPING.items():
        if any(word in name_lower for word in rule_key.lower().split()):
            return rule_data['xpath']
    
    # Fallback to most appropriate rule based on content - be more comprehensive
    if any(phrase in desc_lower for phrase in ['security', 'password', 'username', 'sensitive', 'credential', 'secret']):
        return COMPREHENSIVE_RULESET_MAPPING['DisallowPlaintextSensitiveAttributes']['xpath']
    elif any(phrase in desc_lower for phrase in ['https', 'tls', 'http', 'insecure', 'certificate']):
        return COMPREHENSIVE_RULESET_MAPPING['EnforceTLSInHttpConnections']['xpath']
    elif any(phrase in desc_lower for phrase in ['flow', 'naming', 'convention', 'name']):
        return COMPREHENSIVE_RULESET_MAPPING['FlowNameHyphenatedLowerCase']['xpath']
    elif any(phrase in desc_lower for phrase in ['error', 'exception', 'try', 'catch', 'handler']):
        return COMPREHENSIVE_RULESET_MAPPING['ErrorHandlerExists']['xpath']
    elif any(phrase in desc_lower for phrase in ['documentation', 'comment', 'doc']):
        return COMPREHENSIVE_RULESET_MAPPING['FlowDocumentation']['xpath']
    elif any(phrase in desc_lower for phrase in ['project', 'pom', 'maven', 'parent', 'dependency']):
        return COMPREHENSIVE_RULESET_MAPPING['ProjectPomMustHaveParent']['xpath']
    elif any(phrase in desc_lower for phrase in ['performance', 'memory', 'stream', 'connection']):
        return COMPREHENSIVE_RULESET_MAPPING['AvoidLargePayloadsInMemory']['xpath']
    elif any(phrase in desc_lower for phrase in ['empty', 'unused', 'quality']):
        return COMPREHENSIVE_RULESET_MAPPING['AvoidEmptyFlows']['xpath']
    else:
        # Default to a more comprehensive rule that covers multiple aspects
        return COMPREHENSIVE_RULESET_MAPPING['FlowNameHyphenatedLowerCase']['xpath']

def generate_pdf_report(report_dict, pdf_path):
    """Generate a proper PDF report using reportlab"""
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.darkblue
    )
    
    compliance_style = ParagraphStyle(
        'ComplianceStyle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=15,
        spaceBefore=15,
        alignment=TA_CENTER,
        textColor=colors.darkgreen
    )
    
    normal_style = styles['Normal']
    
    # Title
    title = Paragraph(f"Mule Guardian Code Review Report", title_style)
    story.append(title)
    story.append(Spacer(1, 20))
    
    # Compliance Section
    compliance_percentage = report_dict.get('compliance_percentage', 0)
    compliance_score = report_dict.get('compliance_score', {'status': 'Unknown', 'icon': '?', 'color': 'black'})
    
    compliance_title = Paragraph(f"Project Compliance: {compliance_percentage}% ({compliance_score['status']})", compliance_style)
    story.append(compliance_title)
    story.append(Spacer(1, 15))
    
    # Project Information
    project_info = [
        ['Project Name:', report_dict['project_name']],
        ['Project Path:', report_dict['project_path']],
        ['Ruleset Path:', report_dict['ruleset_path']],
        ['Scan Timestamp:', report_dict['scan_timestamp']],
        ['Files Scanned:', str(report_dict['files_scanned'])],
        ['Scan Duration:', f"{report_dict['scan_duration']:.2f} seconds"],
        ['Compliance Score:', f"{compliance_percentage}% ({compliance_score['status']})"]
    ]
    
    project_table = Table(project_info, colWidths=[2*inch, 4*inch])
    project_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(Paragraph("Project Information", heading_style))
    story.append(project_table)
    story.append(Spacer(1, 20))
    
    # Compliance Recommendations
    compliance_recommendations = get_compliance_recommendations(
        compliance_percentage,
        report_dict.get('violations_by_priority', {})
    )
    
    if compliance_recommendations:
        story.append(Paragraph("Compliance Recommendations", heading_style))
        for recommendation in compliance_recommendations:
            story.append(Paragraph(f"• {recommendation}", normal_style))
        story.append(Spacer(1, 20))
    
    # Summary
    story.append(Paragraph("Summary", heading_style))
    story.append(Paragraph(report_dict['summary'], normal_style))
    story.append(Spacer(1, 20))
    
    # Violations by Priority
    if report_dict['violations_by_priority']:
        story.append(Paragraph("Violations by Priority", heading_style))
        priority_data = [['Priority', 'Count']]
        for priority, count in report_dict['violations_by_priority'].items():
            priority_data.append([priority, str(count)])
        
        priority_table = Table(priority_data, colWidths=[2*inch, 1*inch])
        priority_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(priority_table)
        story.append(Spacer(1, 20))
    
    # Violations by Category
    if report_dict['violations_by_category']:
        story.append(Paragraph("Violations by Category", heading_style))
        category_data = [['Category', 'Count']]
        for category, count in report_dict['violations_by_category'].items():
            category_data.append([category, str(count)])
        
        category_table = Table(category_data, colWidths=[3*inch, 1*inch])
        category_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(category_table)
        story.append(Spacer(1, 20))
    
    # Violations Details
    if report_dict['violations']:
        story.append(Paragraph("Violations Details", heading_style))
        
        # Group violations by file for better organization
        violations_by_file = {}
        for violation in report_dict['violations']:
            file_path = violation['file_path']
            if file_path not in violations_by_file:
                violations_by_file[file_path] = []
            violations_by_file[file_path].append(violation)
        
        for file_path, file_violations in violations_by_file.items():
            story.append(Paragraph(f"File: {file_path}", styles['Heading3']))
            
            # Create table for violations in this file with better column widths
            violation_data = [['Rule', 'Priority', 'Line', 'Message']]
            for violation in file_violations:
                # Truncate rule name if too long
                rule_name = violation['rule']
                if len(rule_name) > 20:
                    rule_name = rule_name[:17] + '...'
                
                # Truncate message if too long
                message = violation['message']
                if len(message) > 40:
                    message = message[:37] + '...'
                
                violation_data.append([
                    rule_name,
                    violation['priority'],
                    str(violation['line']),
                    message
                ])
            
            # Adjust column widths to prevent overlapping
            violation_table = Table(violation_data, colWidths=[1.2*inch, 0.6*inch, 0.4*inch, 3.8*inch])
            violation_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),  # Smaller font size
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('WORDWRAP', (0, 0), (-1, -1), True)  # Enable word wrapping
            ]))
            story.append(violation_table)
            story.append(Spacer(1, 15))
    
    # Build PDF
    doc.build(story)

@app.route('/api/cleanup', methods=['POST'])
def cleanup_files():
    """Clean up temporary files"""
    try:
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        
        cleaned_files = []
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    if os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                    else:
                        os.remove(file_path)
                    cleaned_files.append(file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up {file_path}: {e}")
        
        return jsonify({
            'success': True,
            'cleaned_files': cleaned_files
        })
    
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Mule Guardian Server')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the server on (default: 8080)')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    args = parser.parse_args()
    
    print("🚀 Starting Mule Guardian Server...")
    print(f"📊 Web Interface: http://localhost:{args.port}")
    print(f"🔧 API Endpoints: http://localhost:{args.port}/api/")
    print(f"📋 Health Check: http://localhost:{args.port}/api/health")
    print("\nPress Ctrl+C to stop the server")
    
    app.run(host=args.host, port=args.port, debug=False) 