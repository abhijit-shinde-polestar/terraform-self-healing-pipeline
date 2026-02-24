#!/usr/bin/env python3
"""
Error Classification and Pattern Matching for Terraform/Terragrunt
Provides quick classification before invoking AI agent
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ErrorPattern:
    """Pattern for matching common errors"""
    pattern: str
    category: str
    severity: str
    quick_fix: Optional[str] = None


class TerraformErrorClassifier:
    """Fast error classification using pattern matching"""
    
    PATTERNS = [
        ErrorPattern(
            pattern=r"provider registry\.terraform\.io/[\w-]+/[\w-]+ (\d+\.\d+\.\d+).*doesn't match.*(\d+\.\d+\.\d+)",
            category="provider_version_mismatch",
            severity="medium",
            quick_fix="Update provider version constraint in versions.tf"
        ),
        ErrorPattern(
            pattern=r"Error: Unsupported Terraform Core version",
            category="terraform_version",
            severity="high",
            quick_fix="Update Terraform version or terraform block required_version"
        ),
        ErrorPattern(
            pattern=r"ResourceInUseException|AlreadyExistsException|ConflictException",
            category="resource_conflict",
            severity="high",
            quick_fix="Check for duplicate resources or import existing resource"
        ),
        ErrorPattern(
            pattern=r"ResourceNotFoundException|NoSuchEntity|NotFound",
            category="missing_resource",
            severity="high",
            quick_fix="Create missing dependency or update resource reference"
        ),
        ErrorPattern(
            pattern=r"AccessDenied|UnauthorizedOperation|Forbidden|403",
            category="permission_denied",
            severity="critical",
            quick_fix="Update IAM permissions or role trust policy"
        ),
        ErrorPattern(
            pattern=r"Error acquiring the state lock|state is locked",
            category="state_lock",
            severity="medium",
            quick_fix="Wait for lock release or force-unlock if stale"
        ),
        ErrorPattern(
            pattern=r"Error: Invalid.*syntax|Error: Unsupported block type|Error: Missing required argument",
            category="syntax_error",
            severity="high",
            quick_fix="Fix HCL syntax in configuration files"
        ),
        ErrorPattern(
            pattern=r"Error: Reference to undeclared|depends_on.*not found",
            category="dependency_error",
            severity="high",
            quick_fix="Add missing resource or fix dependency reference"
        ),
        ErrorPattern(
            pattern=r"timeout while waiting|operation timed out|context deadline exceeded",
            category="timeout",
            severity="medium",
            quick_fix="Increase timeout or check resource availability"
        ),
    ]
    
    @classmethod
    def classify(cls, error_output: str) -> Tuple[str, str, Optional[str], List[str]]:
        """Classify error and return category, severity, quick fix, and matched patterns"""
        matched_patterns = []
        categories = []
        severities = []
        quick_fixes = []
        matched_lines = []
        
        for pattern in cls.PATTERNS:
            matches = re.finditer(pattern.pattern, error_output, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                matched_patterns.append(pattern)
                categories.append(pattern.category)
                severities.append(pattern.severity)
                if pattern.quick_fix:
                    quick_fixes.append(pattern.quick_fix)
                
                start = error_output.rfind('\n', 0, match.start()) + 1
                end = error_output.find('\n', match.end())
                if end == -1:
                    end = len(error_output)
                matched_lines.append(error_output[start:end])
        
        if not categories:
            return "unknown", "medium", None, []
        
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        best_idx = min(range(len(severities)), key=lambda i: severity_order.get(severities[i], 99))
        
        return (
            categories[best_idx],
            severities[best_idx],
            quick_fixes[best_idx] if quick_fixes else None,
            list(set(matched_lines))
        )


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: error-classifier.py <error-log-file>")
        sys.exit(1)
    
    with open(sys.argv[1], 'r') as f:
        error_output = f.read()
    
    category, severity, quick_fix, matched_lines = TerraformErrorClassifier.classify(error_output)
    
    print(f"Category: {category}")
    print(f"Severity: {severity}")
    print(f"Quick Fix: {quick_fix or 'None'}")
