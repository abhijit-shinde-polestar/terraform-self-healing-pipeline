#!/usr/bin/env python3
"""
Autonomous Self-Healing AI Agent for Terraform/Terragrunt Deployments
Cross-repository version - analyzes errors and creates fixes in source repos
"""

import os
import sys
import json
import re
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import anthropic


class ErrorCategory(Enum):
    """Classification of infrastructure errors"""
    PROVIDER_VERSION = "provider_version"
    RESOURCE_CONFLICT = "resource_conflict"
    MISSING_RESOURCE = "missing_resource"
    PERMISSION_DENIED = "permission_denied"
    SYNTAX_ERROR = "syntax_error"
    STATE_LOCK = "state_lock"
    DEPENDENCY_ERROR = "dependency_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information about a deployment error"""
    category: ErrorCategory
    error_message: str
    affected_files: List[str]
    suggested_fix: str
    confidence: float
    raw_output: str


@dataclass
class FixResult:
    """Result of applying a fix"""
    success: bool
    message: str
    files_modified: List[str]
    branch_name: str
    commit_sha: str


class SafetyRails:
    """Safety mechanisms to prevent dangerous automated changes"""
    
    MAX_RETRY_ATTEMPTS = 5
    MAX_FILES_PER_FIX = 10
    PROTECTED_PATTERNS = [
        r".*\.tfstate$",
        r".*\.tfstate\.backup$",
        r".*\.terraform\.lock\.hcl$",
    ]
    DANGEROUS_OPERATIONS = [
        "destroy",
        "delete",
        "remove",
        "drop",
    ]
    
    @staticmethod
    def validate_file_changes(files: List[str]) -> Tuple[bool, str]:
        """Validate that file changes are safe"""
        if len(files) > SafetyRails.MAX_FILES_PER_FIX:
            return False, f"Too many files to modify ({len(files)} > {SafetyRails.MAX_FILES_PER_FIX})"
        
        for file_path in files:
            for pattern in SafetyRails.PROTECTED_PATTERNS:
                if re.match(pattern, file_path):
                    return False, f"Attempting to modify protected file: {file_path}"
        
        return True, "Validation passed"
    
    @staticmethod
    def validate_fix_content(content: str) -> Tuple[bool, str]:
        """Validate that fix content doesn't contain dangerous operations"""
        content_lower = content.lower()
        
        for operation in SafetyRails.DANGEROUS_OPERATIONS:
            if operation in content_lower and "resource" in content_lower:
                return False, f"Fix contains potentially dangerous operation: {operation}"
        
        return True, "Content validation passed"


class TerraformErrorAnalyzer:
    """Analyzes Terraform/Terragrunt errors using AI"""
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20241022"
    
    def analyze_error(self, error_output: str, context_files: Dict[str, str]) -> ErrorContext:
        """Analyze error output and generate fix using Claude"""
        
        context = self._build_context(error_output, context_files)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            temperature=0,
            system=self._get_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": context
                }
            ]
        )
        
        return self._parse_ai_response(response.content[0].text, error_output)
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for the AI agent"""
        return """You are an expert DevOps engineer specializing in Terraform and Terragrunt infrastructure automation.
Your task is to analyze deployment errors and provide precise, actionable fixes.

When analyzing errors, you must:
1. Classify the error into one of these categories: provider_version, resource_conflict, missing_resource, permission_denied, syntax_error, state_lock, dependency_error, timeout, unknown
2. Identify the root cause
3. Provide a specific fix with exact file paths and code changes
4. Assign a confidence score (0.0 to 1.0)

CRITICAL SAFETY RULES:
- Never suggest destroying or deleting production resources
- Never modify .tfstate files directly
- Never suggest removing state locks manually unless absolutely necessary
- Always prefer minimal, targeted fixes
- Validate all changes are backwards compatible

Respond in JSON format:
{
  "category": "error_category",
  "confidence": 0.95,
  "root_cause": "Brief explanation",
  "affected_files": ["path/to/file1.tf", "path/to/file2.hcl"],
  "fix": {
    "description": "What this fix does",
    "changes": [
      {
        "file": "path/to/file.tf",
        "action": "replace|add|remove",
        "old_content": "content to replace (if action is replace)",
        "new_content": "new content to add"
      }
    ]
  }
}"""
    
    def _build_context(self, error_output: str, context_files: Dict[str, str]) -> str:
        """Build context for AI analysis"""
        context = f"""# Terraform/Terragrunt Deployment Error

## Error Output:
```
{error_output}
```

## Relevant Files:
"""
        for file_path, content in context_files.items():
            context += f"\n### {file_path}\n```hcl\n{content}\n```\n"
        
        context += "\n\nAnalyze this error and provide a fix in JSON format."
        return context
    
    def _parse_ai_response(self, ai_response: str, raw_output: str) -> ErrorContext:
        """Parse AI response into ErrorContext"""
        try:
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in AI response")
            
            data = json.loads(json_match.group())
            
            return ErrorContext(
                category=ErrorCategory(data.get("category", "unknown")),
                error_message=data.get("root_cause", "Unknown error"),
                affected_files=data.get("affected_files", []),
                suggested_fix=json.dumps(data.get("fix", {}), indent=2),
                confidence=float(data.get("confidence", 0.5)),
                raw_output=raw_output
            )
        except Exception as e:
            print(f"Error parsing AI response: {e}")
            return ErrorContext(
                category=ErrorCategory.UNKNOWN,
                error_message="Failed to parse AI response",
                affected_files=[],
                suggested_fix="",
                confidence=0.0,
                raw_output=raw_output
            )


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI-powered self-healing deployment agent")
    parser.add_argument("--error-log", required=True, help="Path to error log file")
    parser.add_argument("--context-dir", required=True, help="Directory with context files")
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    parser.add_argument("--output", default="fix-result.json", help="Output file for fix result")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Minimum confidence threshold")
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    
    # Read error log
    try:
        with open(args.error_log, 'r') as f:
            error_output = f.read()
    except Exception as e:
        print(f"❌ Error reading log file: {e}")
        sys.exit(1)
    
    # Gather context files
    context_files = {}
    for root, dirs, files in os.walk(args.context_dir):
        if '.terraform' in root or '.git' in root:
            continue
        
        for file in files:
            if file.endswith(('.tf', '.hcl')):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, args.context_dir)
                
                try:
                    with open(file_path, 'r') as f:
                        context_files[rel_path] = f.read()
                except Exception as e:
                    print(f"Warning: Could not read {rel_path}: {e}")
    
    print(f"📁 Gathered {len(context_files)} context files")
    
    # Analyze error
    print("🔍 Analyzing error with AI...")
    analyzer = TerraformErrorAnalyzer(api_key)
    error_context = analyzer.analyze_error(error_output, context_files)
    
    print(f"📊 Category: {error_context.category.value}")
    print(f"📊 Confidence: {error_context.confidence:.2%}")
    print(f"📊 Root Cause: {error_context.error_message}")
    
    # Check confidence threshold
    if error_context.confidence < args.min_confidence:
        print(f"⚠️  Confidence too low ({error_context.confidence:.2%} < {args.min_confidence:.2%})")
        result = {
            "success": False,
            "reason": "low_confidence",
            "confidence": error_context.confidence,
            "category": error_context.category.value,
            "message": error_context.error_message
        }
    else:
        # Validate safety
        is_safe, msg = SafetyRails.validate_file_changes(error_context.affected_files)
        if not is_safe:
            print(f"⚠️  Safety validation failed: {msg}")
            result = {
                "success": False,
                "reason": "safety_violation",
                "message": msg
            }
        else:
            result = {
                "success": True,
                "category": error_context.category.value,
                "confidence": error_context.confidence,
                "message": error_context.error_message,
                "affected_files": error_context.affected_files,
                "fix": json.loads(error_context.suggested_fix)
            }
            print("✅ Fix generated successfully")
    
    # Write output
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"📝 Results written to {args.output}")
    
    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
