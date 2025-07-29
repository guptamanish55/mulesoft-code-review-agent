#!/usr/bin/env python3
"""
Mule Guardian Code Review Agent
Enterprise-level code review tool using PMD for MuleSoft projects
"""

import os
import sys
import json
import subprocess
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass, asdict
from enum import Enum
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Priority(Enum):
    """PMD Priority levels"""
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    INFO = 4

@dataclass
class Violation:
    """Represents a PMD violation"""
    rule: str
    message: str
    priority: Priority
    line: int
    column: int
    file_path: str
    category: str
    description: str
    fix_suggestion: Optional[str] = None

@dataclass
class CodeReviewReport:
    """Complete code review report"""
    project_name: str
    project_path: str
    ruleset_path: str
    scan_timestamp: str
    total_violations: int
    violations_by_priority: Dict[str, int]
    violations_by_category: Dict[str, int]
    violations: List[Violation]
    scan_duration: float
    files_scanned: int
    excluded_files: List[str]
    summary: str
    compliance_percentage: float

class MuleSoftCodeReviewAgent:
    """Intelligent code review agent for MuleSoft projects"""
    
    def __init__(self, project_path: str, ruleset_path: str):
        self.project_path = Path(project_path).resolve()
        self.ruleset_path = Path(ruleset_path).resolve()
        self.excluded_patterns = [
            'target/**',
            '**/target/**',
            '**/target',
            'target',
            '**/settings.xml',
            '**/application-types.xml',
            '**/.git/**',
            '**/node_modules/**',
            '**/.m2/**',
            '**/logs/**',
            '**/*.log',
            '**/.DS_Store',
            '**/Thumbs.db',
            '**/build/**',
            '**/dist/**',
            '**/.idea/**',
            '**/.vscode/**',
            '**/bin/**',
            '**/out/**'
        ]
        
        # Validate paths
        if not self.project_path.exists():
            raise ValueError(f"Project path does not exist: {self.project_path}")
        if not self.ruleset_path.exists():
            raise ValueError(f"Ruleset path does not exist: {self.ruleset_path}")
    
    def check_pmd_installation(self) -> bool:
        """Check if PMD is installed and accessible"""
        try:
            logger.info("Checking PMD installation at /opt/homebrew/bin/pmd")
            result = subprocess.run(['/opt/homebrew/bin/pmd', '--version'], 
                                  capture_output=True, text=True, timeout=30)
            logger.info(f"PMD check result: returncode={result.returncode}, stdout={result.stdout[:100]}, stderr={result.stderr[:100]}")
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"PMD check failed with exception: {e}")
            return False
    
    def get_project_info(self) -> Dict[str, str]:
        """Extract project information from pom.xml or project structure"""
        pom_path = self.project_path / 'pom.xml'
        
        # First try to get info from pom.xml
        if pom_path.exists():
            try:
                tree = ET.parse(pom_path)
                root = tree.getroot()
                
                # Handle namespace
                ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
                
                name = root.find('.//mvn:name', ns)
                version = root.find('.//mvn:version', ns)
                group_id = root.find('.//mvn:groupId', ns)
                
                if name is not None and name.text:
                    return {
                        'name': name.text,
                        'version': version.text if version is not None and version.text else 'Unknown',
                        'groupId': group_id.text if group_id is not None and group_id.text else 'Unknown'
                    }
            except Exception as e:
                logger.warning(f"Could not parse pom.xml: {e}")
        
        # If pom.xml doesn't exist or parsing failed, try to detect project name from structure
        project_name = self._detect_project_name_from_structure()
        
        return {
            'name': project_name,
            'version': 'Unknown',
            'groupId': 'Unknown'
        }
    
    def _detect_project_name_from_structure(self) -> str:
        """Detect project name from project structure and files"""
        # First, try to find the actual project directory within the temp directory
        # The structure is typically: /tmp/mulesoft_project_xxx/actual-project-name/
        for item in self.project_path.iterdir():
            if item.is_dir() and not item.name.startswith('mulesoft_project_'):
                # This is likely the actual project directory
                return item.name
        
        # If we can't find a meaningful name, try to extract from the temp directory path
        # Look for patterns like /private/var/folders/.../mulesoft_project_xxx/project-name/
        temp_path_str = str(self.project_path)
        if 'mulesoft_project_' in temp_path_str:
            # Find the part after mulesoft_project_xxx/
            parts = temp_path_str.split('mulesoft_project_')
            if len(parts) > 1:
                after_temp = parts[1]
                # Split by '/' and take the first meaningful part
                path_parts = after_temp.split('/')
                if len(path_parts) > 1:
                    potential_name = path_parts[1]  # The actual project directory
                    if potential_name and not potential_name.startswith('mulesoft_project_'):
                        return potential_name
        
        # Look for common MuleSoft project indicators
        possible_names = []
        
        # Check for src/main/mule directory structure (typical MuleSoft project)
        mule_dir = self.project_path / 'src' / 'main' / 'mule'
        if mule_dir.exists():
            # Look for API XML files or main configuration files
            for file_path in mule_dir.rglob('*.xml'):
                if file_path.name in ['api.xml', 'main.xml', 'global.xml']:
                    # Try to extract name from file content
                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()
                        
                        # Look for flow names or API names
                        for flow in root.findall('.//{*}flow'):
                            name_attr = flow.get('name')
                            if name_attr and not name_attr.startswith('mulesoft_project_'):
                                # Clean up the name
                                clean_name = name_attr.replace('-flow', '').replace('_flow', '').replace('Flow', '')
                                if clean_name and len(clean_name) > 3:
                                    possible_names.append(clean_name)
                        
                        # Look for API names in RAML files
                        for raml_file in mule_dir.rglob('*.raml'):
                            if 'api' in raml_file.name.lower():
                                name_from_raml = raml_file.stem.replace('-api', '').replace('_api', '')
                                if name_from_raml and len(name_from_raml) > 3:
                                    possible_names.append(name_from_raml)
                    
                    except Exception:
                        continue
        
        # Check for pom.xml artifactId as fallback
        pom_path = self.project_path / 'pom.xml'
        if pom_path.exists():
            try:
                tree = ET.parse(pom_path)
                root = tree.getroot()
                ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
                artifact_id = root.find('.//mvn:artifactId', ns)
                if artifact_id is not None and artifact_id.text:
                    possible_names.append(artifact_id.text)
            except Exception:
                pass
        
        # Check for directory names that look like project names
        for item in self.project_path.iterdir():
            if item.is_dir() and not item.name.startswith('mulesoft_project_'):
                # Look for directories that might contain the actual project
                if any(keyword in item.name.lower() for keyword in ['api', 'service', 'connector', 'integration']):
                    possible_names.append(item.name)
        
        # If we found possible names, return the best one
        if possible_names:
            # Prefer names that look like actual project names
            for name in possible_names:
                if not name.startswith('mulesoft_project_') and len(name) > 3:
                    return name
        
        # Final fallback - try to extract from the path itself
        path_parts = str(self.project_path).split('/')
        for part in reversed(path_parts):
            if part and not part.startswith('mulesoft_project_') and len(part) > 3:
                # Clean up the name
                clean_part = part.replace('-', '').replace('_', '').replace('.', '')
                if clean_part.isalnum() and len(clean_part) > 3:
                    return part
        
        # Last resort - use a generic name
        return "MuleSoft Project"
    
    def create_pmd_exclusions_file(self) -> Path:
        """Create a PMD exclusions file to skip target and settings.xml"""
        exclusions_file = self.project_path / '.pmdignore'
        
        exclusion_patterns = [
            'target/',
            '**/target/**',
            'target',
            '**/target',
            '**/settings.xml',
            '**/application-types.xml',
            '.git/',
            'node_modules/',
            '.m2/',
            'logs/',
            '*.log',
            '.DS_Store',
            'Thumbs.db',
            'build/',
            'dist/',
            '.idea/',
            '.vscode/',
            'bin/',
            'out/'
        ]
        
        with open(exclusions_file, 'w') as f:
            f.write('\n'.join(exclusion_patterns))
        
        return exclusions_file
    
    def run_pmd_analysis(self) -> Tuple[str, float]:
        """Run PMD analysis and return results"""
        start_time = datetime.now()
        
        # Create exclusions file
        exclusions_file = self.create_pmd_exclusions_file()
        
        # Build PMD command with MuleSoft-specific file types
        file_list_path = self._create_file_list()
        
        cmd = [
            '/opt/homebrew/bin/pmd', 'check',
            '--file-list', file_list_path,
            '--rulesets', str(self.ruleset_path),
            '--format', 'xml',
            '--no-cache',
            '--suppress-marker', 'PMD.SuppressWarnings',
            '--encoding', 'UTF-8'
        ]
        
        logger.info(f"Running PMD analysis...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"PMD completed with return code: {result.returncode}")
            if result.stderr:
                logger.info(f"PMD stderr: {result.stderr}")
            
            if result.returncode != 0 and result.returncode != 4:  # PMD returns 4 for violations
                logger.error(f"PMD command failed: {result.stderr}")
                # Check if it's a ruleset error
                if "Exception applying rule" in result.stderr:
                    logger.warning("PMD ruleset has errors, trying alternative analysis")
                    return self._run_alternative_analysis(), duration
                else:
                    raise RuntimeError(f"PMD analysis failed: {result.stderr}")
            
            # If no output, try alternative approach
            if not result.stdout.strip():
                logger.warning("PMD returned no output, trying alternative analysis")
                return self._run_alternative_analysis(), duration
            
            return result.stdout, duration
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("PMD analysis timed out after 5 minutes")
        except FileNotFoundError:
            raise RuntimeError("PMD is not installed. Please install PMD first.")
        finally:
            # Clean up exclusions file
            if exclusions_file.exists():
                exclusions_file.unlink()
    
    def _create_file_list(self) -> str:
        """Create a file list for PMD to analyze specific MuleSoft files"""
        file_list_path = self.project_path / 'pmd-files.txt'
        
        mulesoft_file_patterns = [
            '**/*.xml',      # Mule configuration files
            '**/*.yaml',     # YAML configuration
            '**/*.yml',      # YAML configuration
            '**/*.properties', # Properties files
            '**/*.java',     # Java files
            '**/pom.xml',    # Maven POM
            '**/mule-artifact.json', # Mule artifact descriptor
            '**/*.raml',     # RAML API specifications
            '**/*.wsdl',     # WSDL files
            '**/*.xsd',      # XSD schema files
        ]
        
        files_to_analyze = []
        excluded_count = 0
        
        for pattern in mulesoft_file_patterns:
            # Handle different pattern types
            if pattern.startswith('**/'):
                # Recursive pattern
                for file_path in self.project_path.rglob(pattern[3:]):
                    if file_path.is_file():
                        if self._is_excluded(file_path):
                            excluded_count += 1
                        else:
                            files_to_analyze.append(str(file_path))
            else:
                # Direct pattern
                for file_path in self.project_path.glob(pattern):
                    if file_path.is_file():
                        if self._is_excluded(file_path):
                            excluded_count += 1
                        else:
                            files_to_analyze.append(str(file_path))
        
        # Sort files for consistent ordering
        files_to_analyze.sort()
        
        with open(file_list_path, 'w') as f:
            f.write('\n'.join(files_to_analyze))
        
        logger.info(f"Created file list with {len(files_to_analyze)} files to analyze (excluded {excluded_count} files)")
        return str(file_list_path)
    
    def _is_excluded(self, file_path: Path) -> bool:
        """Check if a file should be excluded from analysis"""
        # Convert to string for easier pattern matching
        file_str = str(file_path)
        
        # Check for target folder in any part of the path
        if 'target' in file_str.split(os.sep):
            return True
        
        # Check for application-types.xml files (exclude from all analysis)
        if 'application-types.xml' in file_str:
            return True
        
        # Check other exclusion patterns
        for pattern in self.excluded_patterns:
            if file_path.match(pattern):
                return True
        
        return False
    
    def _run_alternative_analysis(self) -> str:
        """Run alternative analysis when PMD doesn't work"""
        logger.info("Running alternative analysis for MuleSoft files")
        
        violations = []
        
        # Analyze MuleSoft-specific files
        for file_path in self.project_path.rglob('*.xml'):
            if not self._is_excluded(file_path):
                file_violations = self._analyze_mulesoft_file(file_path)
                violations.extend(file_violations)
        
        # Analyze YAML files
        for file_path in self.project_path.rglob('*.yaml'):
            if not self._is_excluded(file_path):
                file_violations = self._analyze_yaml_file(file_path)
                violations.extend(file_violations)
        
        for file_path in self.project_path.rglob('*.yml'):
            if not self._is_excluded(file_path):
                file_violations = self._analyze_yaml_file(file_path)
                violations.extend(file_violations)
        
        # Analyze pom.xml
        pom_path = self.project_path / 'pom.xml'
        if pom_path.exists() and not self._is_excluded(pom_path):
            file_violations = self._analyze_pom_file(pom_path)
            violations.extend(file_violations)
        
        # Create XML output format
        xml_output = self._create_xml_output(violations)
        return xml_output
    
    def _analyze_mulesoft_file(self, file_path: Path) -> List[Dict]:
        """Analyze a single MuleSoft file for common issues"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Check for common MuleSoft issues with better line detection
            for line_num, line in enumerate(lines, 1):
                # Check for plaintext passwords
                if 'password=' in line and '${' not in line and not line.strip().startswith('<!--'):
                    violations.append({
                        'rule': 'DisallowPlaintextSensitiveAttributes',
                        'message': 'Password attribute should use secure property placeholder',
                        'priority': 1,
                        'line': line_num,
                        'column': line.find('password=') + 1,
                        'file_path': str(file_path)
                    })
                
                # Check for HTTP connections
                if 'http://' in line and 'https://' not in line and not line.strip().startswith('<!--'):
                    violations.append({
                        'rule': 'EnforceTLSInHttpConnections',
                        'message': 'HTTP connections should use HTTPS/TLS',
                        'priority': 1,
                        'line': line_num,
                        'column': line.find('http://') + 1,
                        'file_path': str(file_path)
                    })
                
                # Check for payload logging
                if 'logger' in line and 'payload' in line and not line.strip().startswith('<!--'):
                    violations.append({
                        'rule': 'AvoidLoggingPayload',
                        'message': 'Payload should not be logged directly',
                        'priority': 1,
                        'line': line_num,
                        'column': line.find('logger') + 1,
                        'file_path': str(file_path)
                    })
                
                # Check for hardcoded secrets
                if any(secret in line.lower() for secret in ['client_secret=', 'secret=', 'token=']) and '${' not in line and not line.strip().startswith('<!--'):
                    violations.append({
                        'rule': 'DisallowPlaintextSensitiveAttributes',
                        'message': 'Sensitive attributes should use secure property placeholders',
                        'priority': 1,
                        'line': line_num,
                        'column': 1,
                        'file_path': str(file_path)
                    })
                
                # Check for empty flows
                if '<flow' in line and '</flow>' in line and len(line.strip()) < 20:
                    violations.append({
                        'rule': 'AvoidEmptyFlows',
                        'message': 'Flows should not be empty',
                        'priority': 3,
                        'line': line_num,
                        'column': 1,
                        'file_path': str(file_path)
                    })
                
                # Check for missing error handlers
                if '<mule' in line and not any('error-handler' in l for l in lines):
                    violations.append({
                        'rule': 'CommonGlobalErrorHandlerImplemented',
                        'message': 'Global error handler should be implemented',
                        'priority': 2,
                        'line': line_num,
                        'column': 1,
                        'file_path': str(file_path)
                    })
                
        except Exception as e:
            logger.warning(f"Could not analyze file {file_path}: {e}")
        
        return violations
    
    def _analyze_yaml_file(self, file_path: Path) -> List[Dict]:
        """Analyze a YAML file for common issues"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                # Check for plaintext passwords in YAML
                if 'password:' in line and '${' not in line and not line.strip().startswith('#'):
                    violations.append({
                        'rule': 'DisallowPlaintextSensitiveAttributes',
                        'message': 'Password should use secure property placeholder',
                        'priority': 1,
                        'line': line_num,
                        'column': line.find('password:') + 1,
                        'file_path': str(file_path)
                    })
                
                # Check for HTTP URLs
                if 'http://' in line and 'https://' not in line and not line.strip().startswith('#'):
                    violations.append({
                        'rule': 'EnforceTLSInHttpConnections',
                        'message': 'HTTP URLs should use HTTPS',
                        'priority': 1,
                        'line': line_num,
                        'column': line.find('http://') + 1,
                        'file_path': str(file_path)
                    })
                
                # Check for hardcoded secrets
                if any(secret in line.lower() for secret in ['client_secret:', 'secret:', 'token:']) and '${' not in line and not line.strip().startswith('#'):
                    violations.append({
                        'rule': 'DisallowPlaintextSensitiveAttributes',
                        'message': 'Sensitive values should use secure property placeholders',
                        'priority': 1,
                        'line': line_num,
                        'column': 1,
                        'file_path': str(file_path)
                    })
                
        except Exception as e:
            logger.warning(f"Could not analyze YAML file {file_path}: {e}")
        
        return violations
    
    def _analyze_pom_file(self, file_path: Path) -> List[Dict]:
        """Analyze a POM file for common issues"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                # Check for missing parent
                if '<project>' in line and not any('<parent>' in l for l in lines):
                    violations.append({
                        'rule': 'ProjectPomMustHaveParent',
                        'message': 'Project POM must contain a parent element',
                        'priority': 2,
                        'line': line_num,
                        'column': 1,
                        'file_path': str(file_path)
                    })
                
                # Check for hardcoded values
                if any(pattern in line for pattern in ['<version>', '<groupId>', '<artifactId>']) and '${' not in line:
                    violations.append({
                        'rule': 'AvoidHardcodedValues',
                        'message': 'Avoid hardcoded values in POM',
                        'priority': 3,
                        'line': line_num,
                        'column': 1,
                        'file_path': str(file_path)
                    })
                
        except Exception as e:
            logger.warning(f"Could not analyze POM file {file_path}: {e}")
        
        return violations
    
    def _find_line_number(self, content: str, search_term: str) -> int:
        """Find the line number of a search term in content"""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if search_term in line:
                return i
        return 1
    
    def _create_xml_output(self, violations: List[Dict]) -> str:
        """Create PMD XML output format from violations"""
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<pmd version="6.0.0">']
        
        # Group violations by file
        files_violations = {}
        for violation in violations:
            file_path = violation['file_path']
            if file_path not in files_violations:
                files_violations[file_path] = []
            files_violations[file_path].append(violation)
        
        # Create XML for each file
        for file_path, file_violations in files_violations.items():
            xml_parts.append(f'  <file name="{file_path}">')
            for violation in file_violations:
                # Ensure valid line and column numbers
                line = max(1, violation.get('line', 1))
                column = max(1, violation.get('column', 1))
                
                xml_parts.append(f'    <violation beginline="{line}" endline="{line}" begincolumn="{column}" endcolumn="{column}" rule="{violation["rule"]}" ruleset="MuleSoft" priority="{violation["priority"]}">')
                xml_parts.append(f'      {violation["message"]}')
                xml_parts.append('    </violation>')
            xml_parts.append('  </file>')
        
        xml_parts.append('</pmd>')
        return '\n'.join(xml_parts)
    
    def parse_pmd_xml_output(self, xml_output: str) -> List[Violation]:
        """Parse PMD XML output into Violation objects with precise line targeting"""
        violations = []
        
        logger.info(f"Parsing PMD XML output...")
        ns = {'pmd': 'http://pmd.sourceforge.net/report/2.0.0'}
        
        try:
            root = ET.fromstring(xml_output)
            
            # Count file elements
            file_elements = root.findall('.//pmd:file', ns)
            
            for file_elem in file_elements:
                file_path = file_elem.get('name', '')
                # Clean file path to remove temporary directory prefix
                clean_file_path = self._clean_file_path(file_path)
                
                # Count violation elements per file
                violation_elements = file_elem.findall('.//pmd:violation', ns)
                
                for violation_elem in violation_elements:
                    rule = violation_elem.get('rule', 'Unknown')
                    message = violation_elem.text.strip() if violation_elem.text else violation_elem.get('message', '')
                    priority = int(violation_elem.get('priority', '3'))
                    
                    # Enhanced line number detection with fallbacks
                    line = int(violation_elem.get('beginline', violation_elem.get('line', '0')))
                    end_line = int(violation_elem.get('endline', violation_elem.get('line', '0')))
                    column = int(violation_elem.get('begincolumn', violation_elem.get('column', '0')))
                    end_column = int(violation_elem.get('endcolumn', violation_elem.get('column', '0')))
                    
                    # Ensure line numbers are valid and precise
                    if line <= 0:
                        line = 1
                    if end_line <= 0:
                        end_line = line
                    if column <= 0:
                        column = 1
                    if end_column <= 0:
                        end_column = column
                    
                    # Extract category from rule name with enhanced precision
                    category = self._categorize_rule(rule)
                    
                    # Generate precise fix suggestion with line context
                    fix_suggestion = self._generate_fix_suggestion(rule, message, clean_file_path)
                    
                    # Use clean message without line number appending for professional presentation
                    enhanced_message = message
                    
                    violation = Violation(
                        rule=rule,
                        message=enhanced_message,
                        priority=Priority(priority),
                        line=line,
                        column=column,
                        file_path=clean_file_path,
                        category=category,
                        description=self._get_rule_description(rule),
                        fix_suggestion=fix_suggestion
                    )
                    violations.append(violation)
                    
                                    # Log precise violation details for debugging
                logger.info(f"Violation: {rule} at line {line}:{column} in {clean_file_path}")
                    
        except ET.ParseError as e:
            logger.error(f"Failed to parse PMD XML output: {e}")
            raise RuntimeError(f"Invalid PMD XML output: {e}")
        return violations
    
    def _clean_file_path(self, file_path: str) -> str:
        """Clean file path to show meaningful relative paths instead of temporary directory paths"""
        if not file_path:
            return file_path
        
        # Remove temporary directory prefixes
        temp_patterns = [
            '/private/var/folders/',
            '/tmp/',
            '/var/folders/',
            '/tmp/mulesoft_project_',
            '/private/var/folders/*/T/mulesoft_project_'
        ]
        
        for pattern in temp_patterns:
            if pattern in file_path:
                # Find the actual project directory within the temp directory
                # Structure: /tmp/mulesoft_project_xxx/actual-project-name/src/...
                if 'mulesoft_project_' in file_path:
                    # Split by mulesoft_project_ and find the actual project directory
                    parts = file_path.split('mulesoft_project_')
                    if len(parts) > 1:
                        after_temp = parts[1]
                        # Split by '/' and find the actual project directory
                        path_parts = after_temp.split('/')
                        if len(path_parts) > 1:
                            # The first part after mulesoft_project_xxx/ is the actual project directory
                            actual_project_dir = path_parts[1]
                            if actual_project_dir and not actual_project_dir.startswith('mulesoft_project_'):
                                # Reconstruct the path starting from the actual project directory
                                remaining_path = '/'.join(path_parts[1:])
                                return remaining_path
                
                # If we can't find the project directory, just remove the temp prefix
                # Find the last occurrence of mulesoft_project_ and remove everything before it
                if 'mulesoft_project_' in file_path:
                    last_temp_index = file_path.rfind('mulesoft_project_')
                    if last_temp_index != -1:
                        # Find the next '/' after mulesoft_project_xxx
                        next_slash = file_path.find('/', last_temp_index)
                        if next_slash != -1:
                            return file_path[next_slash + 1:]
        
        return file_path
    
    def _categorize_rule(self, rule_name: str) -> str:
        """Categorize rules into logical groups"""
        rule_lower = rule_name.lower()
        
        # Security rules
        if any(keyword in rule_lower for keyword in ['security', 'secure', 'password', 'token', 'secret', 'tls', 'https', 'injection']):
            return 'Security'
        
        # Naming conventions
        if any(keyword in rule_lower for keyword in ['naming', 'name', 'convention', 'flowname', 'variablenaming', 'apinaming']):
            return 'Naming Conventions'
        
        # Project structure
        if any(keyword in rule_lower for keyword in ['structure', 'project', 'pom', 'parent', 'dependency', 'groupid']):
            return 'Project Structure'
        
        # Performance
        if any(keyword in rule_lower for keyword in ['performance', 'optimization', 'memory', 'stream', 'pooling']):
            return 'Performance'
        
        # Error handling
        if any(keyword in rule_lower for keyword in ['error', 'exception', 'handling', 'try', 'catch']):
            return 'Error Handling'
        
        # Documentation
        if any(keyword in rule_lower for keyword in ['documentation', 'doc', 'comment']):
            return 'Documentation'
        
        # Logging
        if any(keyword in rule_lower for keyword in ['logging', 'log']):
            return 'Logging'
        
        # Code quality (default)
        return 'Code Quality'
    
    def _get_rule_description(self, rule_name: str) -> str:
        """Get description for a rule"""
        descriptions = {
            'AvoidLoggingPayload': 'Prevents logging of sensitive payload data',
            'DisallowPlaintextSensitiveAttributes': 'Ensures sensitive attributes use secure property placeholders',
            'EnforceTLSInHttpConnections': 'Enforces HTTPS/TLS for HTTP connections',
            'DisallowInsecureTLS': 'Prevents insecure TLS configuration that disables certificate validation',
            'AvoidSQLInjection': 'Prevents SQL injection vulnerabilities through parameterized queries',
            'FlowNameHyphenatedLowerCase': 'Ensures flow names follow lowercase-hyphenated convention',
            'FlowVariableNamingConvention': 'Enforces flow variables to start with var prefix and use camelCase',
            'PropertiesFileNameConvention': 'Ensures properties files follow environment-specific naming conventions',
            'ApiSpecificationNaming': 'Ensures API specification files follow proper naming conventions',
            'ProjectPomMustHaveParent': 'Ensures POM files have proper parent configuration',
            'ProjectNameMatchesGitRepo': 'Ensures project name follows kebab-case naming convention',
            'GroupIdMatchesBusinessGroupId': 'Ensures groupId follows organizational standards',
            'AllDependenciesAreMavenized': 'Ensures all dependencies are managed via Maven',
            'EnvironmentSpecificPropertyFiles': 'Promotes environment-specific configuration files',
            'TryScopeNotEmpty': 'Ensures try blocks contain actual processing logic',
            'ErrorHandlerExists': 'Ensures error handling is properly implemented',
            'ProperExceptionHandling': 'Encourages specific exception handling for better error management',
            'AvoidLargePayloadsInMemory': 'Encourages streaming for large payloads to improve memory usage',
            'UseConnectionPooling': 'Ensures database connections use pooling for better performance',
            'FlowDocumentation': 'Ensures flows are properly documented',
            'ApiDocumentation': 'Ensures API endpoints are properly documented',
            'AvoidEmptyFlows': 'Ensures flows contain actual processing logic',
            # Generated ruleset rules
            'SecurityBestPractices': 'Enforces security best practices and standards',
            'NamingConventionCompliance': 'Ensures compliance with naming conventions',
            'ProjectStructureCompliance': 'Ensures proper project structure and organization',
            'ErrorHandlingCompliance': 'Ensures proper error handling implementation',
            'PerformanceCompliance': 'Ensures performance optimization standards',
            'DocumentationCompliance': 'Ensures proper documentation standards',
            'CodeQualityCompliance': 'Ensures code quality standards and best practices',
            'CodeQualityStandards': 'Enforces code quality standards',
            'DocumentationRequirements': 'Ensures documentation requirements are met',
            'PerformanceOptimization': 'Enforces performance optimization practices',
            'ErrorHandlingBestPractices': 'Enforces error handling best practices',
            'SecurityCompliance': 'Ensures security compliance standards',
            'CodeQualityRule': 'General code quality and best practices rule'
        }
        return descriptions.get(rule_name, 'Code quality and best practices rule')
    
    def _generate_fix_suggestion(self, rule: str, message: str, file_path: str) -> Optional[str]:
        """Generate precise fix suggestions based on rule and message with line-specific guidance"""
        suggestions = {
            # Security Rules
            'AvoidLoggingPayload': 'Replace #[payload] with specific data fields or use #[payload.attribute] - Line-specific fix required',
            'DisallowPlaintextSensitiveAttributes': 'Use ${secure::property.name} instead of hardcoded values - Update at exact line location',
            'EnforceTLSInHttpConnections': 'Change HTTP URLs to HTTPS and ensure TLS 1.2+ is configured - Modify URL at specific line',
            'DisallowInsecureTLS': 'Remove insecure="true" or set to "false" to enable certificate validation - Update attribute at line',
            'AvoidSQLInjection': 'Use parameterized queries instead of string concatenation in SQL - Replace concatenation at line',
            'AvoidSensitiveDataInLogs': 'Remove sensitive data from log statements or use secure logging patterns - Update logging at line',
            'RequireSecurityMechanisms': 'Add appropriate security mechanisms (OAuth, API Key, etc.) to the endpoint - Configure security at line',
            'RequireSecurityHeaders': 'Add security headers (X-Frame-Options, X-Content-Type-Options, etc.) - Configure headers at line',
            'CheckClientIdHeaders': 'Add client ID validation in request headers - Implement validation at line',
            
            # Project Structure Rules
            'ProjectPomMustHaveParent': 'Add parent element to POM file with appropriate groupId and version - Insert parent element at line',
            'ProjectNameMatchesGitRepo': 'Update project name to use kebab-case (e.g., "my-mulesoft-api") - Modify name element at line',
            'GroupIdMatchesBusinessGroupId': 'Update groupId to follow organizational standards (e.g., com.company.project) - Modify groupId at line',
            'AllDependenciesAreMavenized': 'Add groupId, artifactId, and version to all dependencies - Update dependency at line',
            'EnvironmentSpecificPropertyFiles': 'Create environment-specific config files (e.g., config-dev.yaml, config-prod.yaml) - Update file reference at line',
            'RequireConfigurationProperties': 'Use configuration properties instead of hardcoded values - Replace with ${config.property} at line',
            'AvoidGlobalConfiguration': 'Move configuration to environment-specific property files - Refactor configuration at line',
            'RequireCommonLibraries': 'Add common library dependencies for shared functionality - Add dependency at line',
            'RequireAutoDiscovery': 'Add autodiscovery configuration for API Gateway - Configure autodiscovery at line',
            
            # Naming Convention Rules
            'FlowNameHyphenatedLowerCase': 'Rename flow to use lowercase with hyphens (e.g., "my-flow-name") - Update name attribute at line',
            'FlowVariableNamingConvention': 'Rename variable to start with "var" followed by camelCase (e.g., "varCustomerId") - Update variableName at line',
            'PropertiesFileNameConvention': 'Rename config file to follow pattern: config-env.yaml (e.g., config-dev.yaml) - Update file reference at line',
            'ApiSpecificationNaming': 'Rename API spec file to follow pattern: api-name-version.raml (e.g., customer-api-v1.raml) - Update file reference at line',
            'PropertiesCamelCaseValidation': 'Use camelCase for property names (e.g., "customerId" instead of "customer_id") - Update property name at line',
            
            # Error Handling Rules
            'TryScopeNotEmpty': 'Add actual processing logic inside the try block - Insert logic at line',
            'ErrorHandlerExists': 'Add error handler to the flow for proper error management - Insert error-handler at line',
            'ProperExceptionHandling': 'Use specific exception types instead of generic Exception - Update exception type at line',
            'CommonGlobalErrorHandlerImplemented': 'Implement a global error handler for consistent error management - Add global error handler at line',
            'ErrorHandlerMustHaveOnErrorPropagate': 'Add on-error-propagate to error handler for proper error propagation - Update error handler at line',
            'AvoidEmptyTryScope': 'Add processing logic inside try block or remove empty try scope - Add logic or remove try block at line',
            
            # Performance Rules
            'AvoidLargePayloadsInMemory': 'Use streaming for large payloads instead of loading entirely into memory - Update payload handling at line',
            'UseConnectionPooling': 'Add connectionPoolingSize attribute to database configuration - Add attribute at line',
            'AvoidNestedLoops': 'Refactor nested loops to improve performance - Optimize loop structure at line',
            'AvoidDeepNestingInFlows': 'Reduce flow nesting depth for better maintainability - Refactor flow structure at line',
            'AvoidDuplicateProcessing': 'Remove duplicate processing logic - Consolidate duplicate code at line',
            'DatabaseConnectionPoolConfiguration': 'Configure proper connection pooling for database connections - Add pooling configuration at line',
            'HTTPRequestTimeoutConfiguration': 'Add timeout configuration to HTTP requests - Configure timeout at line',
            
            # Documentation Rules
            'RequireDocumentationForFlows': 'Add documentation comments before the flow definition - Insert comment at line',
            'FlowDocumentation': 'Add documentation comments before the flow definition - Insert comment at line',
            'ApiDocumentation': 'Add documentation comments before the API endpoint - Insert comment at line',
            
            # Code Quality Rules
            'AvoidEmptyFlows': 'Add processing logic to the flow or remove if unused - Add logic or remove flow at line',
            'AvoidEmptyVariable': 'Remove unused variables or assign meaningful values - Update variable at line',
            'AvoidUnusedVariables': 'Remove unused variables or use them in the flow - Remove or utilize variable at line',
            'AvoidHardcodedValues': 'Replace hardcoded values with configuration properties - Use ${config.property} at line',
            'AvoidComplexDataWeaveInTransform': 'Simplify complex DataWeave transformations - Refactor transformation at line',
            'AvoidJsonLoggerForJava17': 'Use structured logging instead of JSON logger for Java 17+ - Update logger configuration at line',
            'LoggerVerbosityLevelForPayload': 'Set appropriate log level for payload logging - Configure log level at line',
            'AvoidDebugInfoInProduction': 'Remove debug logging statements for production deployment - Remove debug logs at line',
            
            # API and Integration Rules
            'APIKitRouterMustBeConfigured': 'Configure APIKit router properly - Add router configuration at line',
            'APIKitConfigMustReferenceRAML': 'Ensure APIKit configuration references RAML specification - Update APIKit config at line',
            'RAMLApiSpecAsExchangeDependency': 'Add RAML API specification as Exchange dependency - Add dependency at line',
            'WSDLAndXSDInCorrectFolder': 'Move WSDL and XSD files to correct folder structure - Reorganize files at line',
            'PreferSubFlowsOverFlowRef': 'Use sub-flows instead of flow-ref for better maintainability - Replace flow-ref with sub-flow at line',
            
            # Testing Rules
            'MUnitTestMustHaveAssertions': 'Add assertions to MUnit test cases - Add assertion statements at line',
            'MocksMustBeClearedAfterTest': 'Clear mocks after each test to prevent test interference - Add mock cleanup at line',
            
            # Monitoring and Logging Rules
            'CorrelationIdLogging': 'Add correlation ID logging for request tracing - Implement correlation ID at line',
            'TransactionStateLogging': 'Add transaction state logging for monitoring - Add transaction logging at line',
            'RequireMonitoringConfiguration': 'Configure monitoring and alerting for the application - Add monitoring config at line',
            
            # Version and Dependency Rules
            'VersionAlignmentRule': 'Align dependency versions across the project - Update version at line',
            
            # Generated ruleset suggestions with line precision
            'SecurityBestPractices': 'Review and implement security best practices as per organizational standards - Apply at specific line location',
            'NamingConventionCompliance': 'Follow established naming conventions for consistency - Update naming at line',
            'ProjectStructureCompliance': 'Ensure project structure follows organizational standards - Modify structure at line',
            'ErrorHandlingCompliance': 'Implement proper error handling as per organizational standards - Add error handling at line',
            'PerformanceCompliance': 'Optimize performance according to organizational standards - Optimize code at line',
            'DocumentationCompliance': 'Add proper documentation as per organizational requirements - Add documentation at line',
            'CodeQualityCompliance': 'Review and improve code quality according to standards - Improve code at line',
            'CodeQualityStandards': 'Follow established code quality standards - Apply standards at line',
            'DocumentationRequirements': 'Add required documentation as specified - Add documentation at line',
            'PerformanceOptimization': 'Optimize performance according to best practices - Optimize at line',
            'ErrorHandlingBestPractices': 'Implement error handling best practices - Add error handling at line',
            'SecurityCompliance': 'Ensure security compliance as per organizational standards - Apply security at line',
            'CodeQualityRule': 'Review and improve code quality according to best practices - Improve at line'
        }
        
        # Return specific suggestion if available, otherwise provide a generic one
        if rule in suggestions:
            return suggestions[rule]
        else:
            # Generate a generic but helpful suggestion based on the rule name and category
            category = self._categorize_rule(rule)
            if 'Security' in category:
                return f'Review and implement security best practices for {rule} - Apply security measures at line'
            elif 'Error' in category:
                return f'Implement proper error handling for {rule} - Add error handling at line'
            elif 'Performance' in category:
                return f'Optimize performance for {rule} - Improve performance at line'
            elif 'Documentation' in category:
                return f'Add proper documentation for {rule} - Add documentation at line'
            elif 'Naming' in category:
                return f'Follow naming conventions for {rule} - Update naming at line'
            elif 'Project' in category:
                return f'Ensure project structure compliance for {rule} - Update project structure at line'
            else:
                return f'Review and improve code quality for {rule} - Apply best practices at line'
    
    def count_files_scanned(self) -> int:
        """Count the number of files that would be scanned"""
        count = 0
        for root, dirs, files in os.walk(self.project_path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if not any(
                Path(root) / d == Path(pattern.replace('**/', '')) 
                for pattern in self.excluded_patterns
            )]
            
            for file in files:
                if file.endswith(('.xml', '.java', '.yaml', '.yml')):
                    file_path = Path(root) / file
                    if not any(file_path.match(pattern) for pattern in self.excluded_patterns):
                        count += 1
        
        return count
    
    def generate_report(self, violations: List[Violation], scan_duration: float) -> CodeReviewReport:
        """Generate comprehensive code review report"""
        project_info = self.get_project_info()
        
        # Calculate statistics
        violations_by_priority = {}
        violations_by_category = {}
        
        for violation in violations:
            priority_key = violation.priority.name
            violations_by_priority[priority_key] = violations_by_priority.get(priority_key, 0) + 1
            
            category = violation.category
            violations_by_category[category] = violations_by_category.get(category, 0) + 1
        
        # Generate summary
        total_violations = len(violations)
        high_priority = violations_by_priority.get('HIGH', 0)
        medium_priority = violations_by_priority.get('MEDIUM', 0)
        
        if total_violations == 0:
            summary = "✅ Excellent! No code quality issues found."
        elif high_priority == 0:
            summary = f"⚠️  {total_violations} issues found, but none are high priority. Review medium and low priority items."
        else:
            summary = f"🚨 {high_priority} high priority issues found! Immediate attention required."
        
        files_scanned = self.count_files_scanned()
        
        # Get clean project path and ruleset path
        clean_project_path = self._get_clean_project_path()
        clean_ruleset_path = self._get_clean_ruleset_path()
        
        # Calculate compliance percentage
        high_violations = violations_by_priority.get('HIGH', 0)
        medium_violations = violations_by_priority.get('MEDIUM', 0)
        low_violations = violations_by_priority.get('LOW', 0)
        
        # Weighted deduction: HIGH=3 points, MEDIUM=2 points, LOW=1 point
        total_deduction = (high_violations * 3) + (medium_violations * 2) + (low_violations * 1)
        compliance_percentage = max(20.0, 100.0 - total_deduction)  # Minimum 20% compliance
        
        return CodeReviewReport(
            project_name=project_info['name'],
            project_path=clean_project_path,
            ruleset_path=clean_ruleset_path,
            scan_timestamp=datetime.now().isoformat(),
            total_violations=total_violations,
            violations_by_priority=violations_by_priority,
            violations_by_category=violations_by_category,
            violations=violations,
            scan_duration=scan_duration,
            files_scanned=files_scanned,
            excluded_files=[],  # Could be enhanced to track excluded files
            summary=summary,
            compliance_percentage=compliance_percentage
        )
    
    def _get_clean_project_path(self) -> str:
        """Get a clean project path that shows the actual project name instead of temporary directory paths"""
        project_info = self.get_project_info()
        project_name = project_info['name']
        
        # If we have a meaningful project name from pom.xml, use it
        if project_name and project_name != 'Unknown' and not project_name.startswith('mulesoft_project_'):
            return f"{project_name}/"
        
        # Look for the actual project directory within the temp directory
        # The structure is typically: /tmp/mulesoft_project_xxx/actual-project-name/
        for item in self.project_path.iterdir():
            if item.is_dir() and not item.name.startswith('mulesoft_project_'):
                # This is likely the actual project directory
                return f"{item.name}/"
        
        # If we can't find a meaningful name, try to extract from the temp directory path
        # Look for patterns like /private/var/folders/.../mulesoft_project_xxx/project-name/
        temp_path_str = str(self.project_path)
        if 'mulesoft_project_' in temp_path_str:
            # Find the part after mulesoft_project_xxx/
            parts = temp_path_str.split('mulesoft_project_')
            if len(parts) > 1:
                after_temp = parts[1]
                # Split by '/' and take the first meaningful part
                path_parts = after_temp.split('/')
                if len(path_parts) > 1:
                    potential_name = path_parts[1]  # The actual project directory
                    if potential_name and not potential_name.startswith('mulesoft_project_'):
                        return f"{potential_name}/"
        
        # Fallback to project name from pom.xml or directory structure
        return f"{project_name}/"
    
    def _get_clean_ruleset_path(self) -> str:
        """Get a clean ruleset path that shows the actual filename"""
        ruleset_filename = os.path.basename(self.ruleset_path)
        
        # If it's a generated ruleset from checklist, show a meaningful name
        if 'ruleset_' in ruleset_filename and '_from_checklist.xml' in ruleset_filename:
            return "Generated Ruleset from Checklist Template"
        elif 'comprehensive-mulesoft-ruleset' in ruleset_filename:
            # For comprehensive rulesets, show the actual filename
            if 'no-debug' in ruleset_filename:
                return "comprehensive-mulesoft-ruleset-no-debug.xml"
            elif 'fixed' in ruleset_filename:
                return "comprehensive-mulesoft-ruleset-fixed.xml"
            else:
                return "comprehensive-mulesoft-ruleset.xml"
        else:
            # For uploaded PMD ruleset files, show the original filename
            # The server adds timestamp prefix: ruleset_YYYYMMDD_HHMMSS_originalname.xml
            if ruleset_filename.startswith('ruleset_') and '_' in ruleset_filename:
                # Split by underscore and look for the original filename
                parts = ruleset_filename.split('_')
                if len(parts) >= 4:  # ruleset_YYYYMMDD_HHMMSS_originalname.xml
                    # Skip 'ruleset', date, and time parts
                    original_name = '_'.join(parts[3:])
                    if original_name and original_name.endswith('.xml'):
                        return original_name
                elif len(parts) >= 3:  # ruleset_YYYYMMDD_originalname.xml
                    original_name = '_'.join(parts[2:])
                    if original_name and original_name.endswith('.xml'):
                        return original_name
            
            # If no timestamp pattern, return the filename as is
            return ruleset_filename
    
    def save_report_json(self, report: CodeReviewReport, output_path: str):
        """Save report as JSON"""
        report_dict = asdict(report)
        # Convert Priority enum to string for JSON serialization
        for violation in report_dict['violations']:
            violation['priority'] = violation['priority'].name
        
        with open(output_path, 'w') as f:
            json.dump(report_dict, f, indent=2)
    
    def run_review(self, output_path: Optional[str] = None, analysis_mode: str = 'comprehensive', priority_filter: str = 'all') -> CodeReviewReport:
        """Run complete code review process with advanced options"""
        logger.info(f"Starting Mule Guardian code review with mode: {analysis_mode}, priority filter: {priority_filter}...")
        
        # Check PMD installation
        if not self.check_pmd_installation():
            raise RuntimeError("PMD is not installed or not accessible. Please install PMD first.")
        
        # Run PMD analysis
        xml_output, scan_duration = self.run_pmd_analysis()
        
        # Parse results
        violations = self.parse_pmd_xml_output(xml_output)
        
        # Apply priority filter
        if priority_filter != 'all':
            violations = self._apply_priority_filter(violations, priority_filter)
            logger.info(f"Applied priority filter '{priority_filter}': {len(violations)} violations remaining")
        
        # Apply analysis mode
        if analysis_mode != 'comprehensive':
            violations = self._apply_analysis_mode(violations, analysis_mode)
            logger.info(f"Applied analysis mode '{analysis_mode}': {len(violations)} violations remaining")
        
        # Generate report
        report = self.generate_report(violations, scan_duration)
        
        # Save report if output path provided
        if output_path:
            self.save_report_json(report, output_path)
            logger.info(f"Report saved to: {output_path}")
        
        logger.info(f"Code review completed. Found {report.total_violations} violations.")
        return report
    
    def _apply_priority_filter(self, violations: List[Violation], priority_filter: str) -> List[Violation]:
        """Apply priority filter to violations"""
        if priority_filter == 'all':
            return violations
        elif priority_filter == 'high':
            return [v for v in violations if v.priority == Priority.HIGH]
        elif priority_filter == 'medium+':
            return [v for v in violations if v.priority in [Priority.HIGH, Priority.MEDIUM]]
        elif priority_filter == 'low+':
            return [v for v in violations if v.priority in [Priority.HIGH, Priority.MEDIUM, Priority.LOW]]
        else:
            return violations
    
    def _apply_analysis_mode(self, violations: List[Violation], analysis_mode: str) -> List[Violation]:
        """Apply analysis mode filter to violations"""
        if analysis_mode == 'comprehensive':
            return violations
        elif analysis_mode == 'security':
            # Focus on security-related violations
            security_categories = ['Security', 'Security Compliance', 'Security Best Practices']
            return [v for v in violations if v.category in security_categories]
        elif analysis_mode == 'performance':
            # Focus on performance-related violations
            performance_categories = ['Performance', 'Performance Compliance', 'Performance Optimization']
            return [v for v in violations if v.category in performance_categories]
        elif analysis_mode == 'custom':
            # For custom rules, return all violations (could be enhanced with custom filtering)
            return violations
        else:
            return violations

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Mule Guardian Code Review Agent')
    parser.add_argument('project_path', help='Path to MuleSoft project directory')
    parser.add_argument('ruleset_path', help='Path to PMD ruleset XML file')
    parser.add_argument('--output', '-o', help='Output JSON report file path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    try:
        agent = MuleSoftCodeReviewAgent(args.project_path, args.ruleset_path)
        report = agent.run_review(args.output)
        
        # Print summary to console
        print(f"\n{'='*60}")
        print(f"CODE REVIEW SUMMARY")
        print(f"{'='*60}")
        print(f"Project: {report.project_name}")
        print(f"Scan Duration: {report.scan_duration:.2f} seconds")
        print(f"Files Scanned: {report.files_scanned}")
        print(f"Total Violations: {report.total_violations}")
        print(f"Summary: {report.summary}")
        
        if report.total_violations > 0:
            print(f"\nViolations by Priority:")
            for priority, count in report.violations_by_priority.items():
                print(f"  {priority}: {count}")
            
            print(f"\nViolations by Category:")
            for category, count in report.violations_by_category.items():
                print(f"  {category}: {count}")
        
        print(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"Code review failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 
