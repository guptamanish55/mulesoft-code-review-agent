#!/usr/bin/env python3
"""
Compliance Configuration Management
Centralized configuration for compliance score calculation
"""

import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class ComplianceConfig:
    """Configuration for compliance score calculation"""
    # Compliance component weights (must sum to 100)
    file_based_weight: float = 70.0  # Percentage weight for file-based compliance
    severity_based_weight: float = 30.0  # Percentage weight for severity-based compliance
    
    # Priority violation weights
    priority_weights: Dict[str, int] = None
    
    # Minimum compliance score
    minimum_compliance: float = 0.0
    
    def __post_init__(self):
        """Initialize default values and validate configuration"""
        if self.priority_weights is None:
            self.priority_weights = {
                'HIGH': 10,    # Critical security/functionality issues
                'MEDIUM': 5,   # Important code quality issues  
                'LOW': 2,      # Minor style/convention issues
                'INFO': 1      # Informational suggestions
            }
        
        # Validate weights sum to 100
        total_weight = self.file_based_weight + self.severity_based_weight
        if abs(total_weight - 100.0) > 0.1:  # Allow small floating point differences
            logger.warning(f"Compliance weights sum to {total_weight}%, adjusting to 100%")
            # Normalize weights to sum to 100
            self.file_based_weight = (self.file_based_weight / total_weight) * 100
            self.severity_based_weight = (self.severity_based_weight / total_weight) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ComplianceConfig':
        """Create from dictionary"""
        return cls(
            file_based_weight=config_dict.get('file_based_weight', 70.0),
            severity_based_weight=config_dict.get('severity_based_weight', 30.0),
            priority_weights=config_dict.get('priority_weights', {
                'HIGH': 10, 'MEDIUM': 5, 'LOW': 2, 'INFO': 1
            }),
            minimum_compliance=config_dict.get('minimum_compliance', 0.0)
        )

class ComplianceConfigManager:
    """Manager for compliance configuration loading and saving"""
    
    DEFAULT_CONFIG_FILE = 'compliance_config.json'
    
    @staticmethod
    def load_config(config_file: Optional[str] = None) -> ComplianceConfig:
        """Load compliance configuration from file or environment variables"""
        config = ComplianceConfig()
        
        # Try to load from file first
        if config_file or os.path.exists(ComplianceConfigManager.DEFAULT_CONFIG_FILE):
            config_path = config_file or ComplianceConfigManager.DEFAULT_CONFIG_FILE
            try:
                with open(config_path, 'r') as f:
                    config_dict = json.load(f)
                config = ComplianceConfig.from_dict(config_dict)
                logger.info(f"Loaded compliance configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}. Using defaults.")
        
        # Override with environment variables if present
        config = ComplianceConfigManager._load_from_env(config)
        
        return config
    
    @staticmethod
    def _load_from_env(config: ComplianceConfig) -> ComplianceConfig:
        """Load configuration from environment variables"""
        # File-based weight
        if 'COMPLIANCE_FILE_WEIGHT' in os.environ:
            try:
                config.file_based_weight = float(os.environ['COMPLIANCE_FILE_WEIGHT'])
            except ValueError:
                logger.warning("Invalid COMPLIANCE_FILE_WEIGHT, using default")
        
        # Severity-based weight
        if 'COMPLIANCE_SEVERITY_WEIGHT' in os.environ:
            try:
                config.severity_based_weight = float(os.environ['COMPLIANCE_SEVERITY_WEIGHT'])
            except ValueError:
                logger.warning("Invalid COMPLIANCE_SEVERITY_WEIGHT, using default")
        
        # Priority weights
        priority_mapping = {
            'COMPLIANCE_HIGH_WEIGHT': 'HIGH',
            'COMPLIANCE_MEDIUM_WEIGHT': 'MEDIUM',
            'COMPLIANCE_LOW_WEIGHT': 'LOW',
            'COMPLIANCE_INFO_WEIGHT': 'INFO'
        }
        
        for env_var, priority in priority_mapping.items():
            if env_var in os.environ:
                try:
                    config.priority_weights[priority] = int(os.environ[env_var])
                except ValueError:
                    logger.warning(f"Invalid {env_var}, using default")
        
        # Minimum compliance
        if 'COMPLIANCE_MINIMUM' in os.environ:
            try:
                config.minimum_compliance = float(os.environ['COMPLIANCE_MINIMUM'])
            except ValueError:
                logger.warning("Invalid COMPLIANCE_MINIMUM, using default")
        
        # Re-validate after loading from environment
        config.__post_init__()
        
        return config
    
    @staticmethod
    def save_config(config: ComplianceConfig, config_file: Optional[str] = None) -> bool:
        """Save compliance configuration to file"""
        config_path = config_file or ComplianceConfigManager.DEFAULT_CONFIG_FILE
        try:
            with open(config_path, 'w') as f:
                json.dump(config.to_dict(), f, indent=2)
            logger.info(f"Saved compliance configuration to {config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config to {config_path}: {e}")
            return False
    
    @staticmethod
    def create_sample_config(config_file: str = 'compliance_config_sample.json'):
        """Create a sample configuration file"""
        sample_config = {
            "file_based_weight": 70.0,
            "severity_based_weight": 30.0,
            "priority_weights": {
                "HIGH": 10,
                "MEDIUM": 5,
                "LOW": 2,
                "INFO": 1
            },
            "minimum_compliance": 0.0,
            "_description": {
                "file_based_weight": "Percentage weight for clean files compliance (0-100)",
                "severity_based_weight": "Percentage weight for severity-adjusted compliance (0-100)",
                "priority_weights": "Weight multipliers for each violation priority level",
                "minimum_compliance": "Minimum compliance score (0-100)"
            }
        }
        
        try:
            with open(config_file, 'w') as f:
                json.dump(sample_config, f, indent=2)
            logger.info(f"Created sample configuration file: {config_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to create sample config: {e}")
            return False

def calculate_compliance_percentage(report, config: Optional[ComplianceConfig] = None) -> float:
    """
    Calculate compliance percentage based on violations and files scanned
    using configurable weights
    
    Args:
        report: Report object with violations and file information
        config: ComplianceConfig object with weights, defaults to standard config
    
    Returns:
        float: Compliance percentage (0-100)
    """
    if config is None:
        config = ComplianceConfigManager.load_config()
    
    try:
        total_files = getattr(report, 'files_scanned', 0)
        total_violations = getattr(report, 'total_violations', 0)
        
        if total_files == 0:
            return config.minimum_compliance
        
        # Calculate files with violations
        files_with_violations = set()
        violations = getattr(report, 'violations', [])
        
        for violation in violations:
            file_path = getattr(violation, 'file_path', None)
            if file_path:
                files_with_violations.add(file_path)
        
        files_with_violations_count = len(files_with_violations)
        clean_files = total_files - files_with_violations_count
        
        # Factor 1: File-based compliance (configurable weight)
        file_based_compliance = (clean_files / total_files) * 100
        
        # Factor 2: Severity-adjusted compliance (configurable weight)
        violations_by_priority = getattr(report, 'violations_by_priority', {})
        total_severity_score = 0
        
        for priority, count in violations_by_priority.items():
            weight = config.priority_weights.get(priority, 1)
            total_severity_score += count * weight
        
        # Calculate severity-adjusted compliance
        if files_with_violations_count > 0 and total_violations > 0:
            # More realistic severity penalty calculation
            # Base penalty on violations per file with progressive scaling
            violations_per_file = total_violations / total_files
            
            # Progressive penalty scale: more violations per file = higher penalty
            if violations_per_file <= 1:
                base_penalty = violations_per_file * 15  # Up to 15% penalty
            elif violations_per_file <= 3:
                base_penalty = 15 + (violations_per_file - 1) * 20  # 15-55% penalty
            elif violations_per_file <= 5:
                base_penalty = 55 + (violations_per_file - 3) * 15  # 55-85% penalty
            else:
                base_penalty = 85 + min(15, (violations_per_file - 5) * 3)  # 85-100% penalty
            
            # Apply severity weighting
            high_weight = config.priority_weights.get('HIGH', 10)
            medium_weight = config.priority_weights.get('MEDIUM', 5)
            low_weight = config.priority_weights.get('LOW', 2)
            
            # Calculate weighted severity multiplier
            high_violations = violations_by_priority.get('HIGH', 0)
            medium_violations = violations_by_priority.get('MEDIUM', 0)
            low_violations = violations_by_priority.get('LOW', 0)
            
            if total_violations > 0:
                severity_multiplier = (
                    (high_violations * high_weight + 
                     medium_violations * medium_weight + 
                     low_violations * low_weight) / 
                    (total_violations * low_weight)  # Normalize against LOW weight baseline
                )
                severity_multiplier = min(2.0, severity_multiplier)  # Cap at 2x multiplier
            else:
                severity_multiplier = 1.0
            
            # Apply severity multiplier to base penalty
            final_penalty = min(100, base_penalty * severity_multiplier)
            severity_adjusted_compliance = max(0, 100 - final_penalty)
        else:
            severity_adjusted_compliance = 100
        
        # Combine both metrics using configurable weights
        final_compliance = (
            (file_based_compliance * config.file_based_weight / 100) + 
            (severity_adjusted_compliance * config.severity_based_weight / 100)
        )
        
        # Apply minimum compliance constraint
        final_compliance = max(config.minimum_compliance, final_compliance)
        
        return round(final_compliance, 2)
        
    except Exception as e:
        logger.error(f"Error calculating compliance percentage: {e}")
        return config.minimum_compliance if config else 0.0

# Utility functions for easy integration
def get_default_config() -> ComplianceConfig:
    """Get default compliance configuration"""
    return ComplianceConfig()

def load_config_from_file(config_file: str) -> ComplianceConfig:
    """Load configuration from specific file"""
    return ComplianceConfigManager.load_config(config_file)

def create_custom_config(file_weight: float = 70.0, severity_weight: float = 30.0, 
                        high_weight: int = 10, medium_weight: int = 5, 
                        low_weight: int = 2, info_weight: int = 1) -> ComplianceConfig:
    """Create custom compliance configuration"""
    return ComplianceConfig(
        file_based_weight=file_weight,
        severity_based_weight=severity_weight,
        priority_weights={
            'HIGH': high_weight,
            'MEDIUM': medium_weight,
            'LOW': low_weight,
            'INFO': info_weight
        }
    )
