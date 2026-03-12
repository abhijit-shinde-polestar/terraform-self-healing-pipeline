#!/usr/bin/env python3
"""
AI-Powered Terraform/Terragrunt Healing Agent

This script uses Claude AI (Anthropic) to automatically analyze and fix 
Terraform/Terragrunt deployment errors. It integrates with GitHub Actions
to provide autonomous error resolution in CI/CD pipelines.

The agent analyzes error logs, examines the codebase context, and generates
structured fixes that can be automatically applied to resolve deployment issues.
"""

import os
import sys
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import anthropic
except ImportError:
    print("❌ Error: anthropic package not installed")
    print("Install with: pip install anthropic")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('ai-healing-agent.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class FixAction:
    """Represents a single file modification action."""
    path: str
    action: str  # 'update', 'create', 'delete'
    content: Optional[str] = None
    reason: str = ""

@dataclass
class HealingResult:
    """Result of the healing analysis."""
    success: bool
    confidence: float
    error_category: str
    fix_summary: str
    actions: List[FixAction]
    reasoning: str
    warnings: List[str]
    estimated_time: str

class TerraformHealingAgent:
    """AI agent for analyzing and fixing Terraform/Terragrunt errors."""
    
    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        """Initialize the healing agent."""
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = 4000
        
    def analyze_and_fix(self, 
                       error_logs: str, 
                       repo_path: str, 
                       terragrunt_path: str,
                       environment: str) -> HealingResult:
        """Analyze error logs and generate fixes."""
        logger.info(f"🔍 Starting analysis for {terragrunt_path} in {environment}")
        
        try:
            # Gather context
            context = self._gather_context(repo_path, terragrunt_path)
            
            # Create prompt
            prompt = self._create_analysis_prompt(error_logs, context, environment)
            
            # Query AI
            response = self._query_claude(prompt)
            
            # Parse response
            result = self._parse_ai_response(response)
            
            logger.info(f"✅ Analysis complete. Confidence: {result.confidence:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Analysis failed: {str(e)}")
            return HealingResult(
                success=False,
                confidence=0.0,
                error_category="analysis_error",
                fix_summary=f"Failed to analyze error: {str(e)}",
                actions=[],
                reasoning="Internal analysis error occurred",
                warnings=[f"Analysis error: {str(e)}"],
                estimated_time="0 minutes"
            )
    
    def _gather_context(self, repo_path: str, terragrunt_path: str) -> Dict[str, Any]:
        """Gather context from the repository."""
        logger.info("📂 Gathering repository context...")
        
        context = {
            "files": {},
            "structure": [],
            "terragrunt_config": None,
            "terraform_files": [],
            "dependencies": []
        }
        
        try:
            base_path = Path(repo_path) / terragrunt_path
            if not base_path.exists():
                logger.warning(f"⚠️  Path not found: {base_path}")
                return context
            
            # Read key files
            key_files = [
                "terragrunt.hcl",
                "main.tf", 
                "variables.tf",
                "outputs.tf",
                "versions.tf",
                "providers.tf"
            ]
            
            for file_name in key_files:
                file_path = base_path / file_name
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding='utf-8')
                        context["files"][file_name] = content
                        logger.info(f"📄 Read {file_name} ({len(content)} chars)")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not read {file_name}: {e}")
            
            # Get directory structure
            try:
                for item in base_path.rglob('*'):
                    if item.is_file() and item.suffix in ['.tf', '.hcl', '.yaml', '.yml']:
                        rel_path = item.relative_to(base_path)
                        context["structure"].append(str(rel_path))
            except Exception as e:
                logger.warning(f"⚠️  Could not scan directory: {e}")
            
            logger.info(f"📊 Context gathered: {len(context['files'])} files, {len(context['structure'])} items")
            
        except Exception as e:
            logger.error(f"❌ Failed to gather context: {e}")
        
        return context
    
    def _create_analysis_prompt(self, error_logs: str, context: Dict, environment: str) -> str:
        """Create the analysis prompt for Claude."""
        return f'''You are an expert Terraform/Terragrunt DevOps engineer. Analyze the deployment error and provide a fix.

ERROR LOGS:

{error_logs[:3000]}  # Truncate long logs


CONTEXT:
Environment: {environment}
Files in repository:
{json.dumps(context["files"], indent=2)[:2000]}

Directory structure:
{json.dumps(context["structure"], indent=2)[:1000]}

ANALYSIS REQUIRED:
1. Identify the root cause of the error
2. Classify the error type
3. Provide a confidence score (0.0-1.0)
4. Generate specific file changes to fix the issue
5. Explain the reasoning

RESPONSE FORMAT (JSON only):
{{
  "success": true,
  "confidence": 0.85,
  "error_category": "provider_version_mismatch",
  "fix_summary": "Update provider version constraints",
  "actions": [
    {{
      "path": "versions.tf",
      "action": "update",
      "content": "terraform {{\n  required_providers {{\n    aws = {{\n      source = \"hashicorp/aws\"\n      version = \"~> 5.0\"\n    }}\n  }}\n}}",
      "reason": "Fix version constraint"
    }}
  ],
  "reasoning": "The error indicates...",
  "warnings": [],
  "estimated_time": "2-3 minutes"
}}

IMPORTANT:
- Only return valid JSON
- Keep file content concise
- Never modify state files
- Confidence must be realistic
- Provide clear reasoning
'''
    
    def _query_claude(self, prompt: str) -> str:
        """Query Claude API."""
        logger.info("🤖 Querying Claude API...")
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            response_text = message.content[0].text
            logger.info(f"✅ Received response ({len(response_text)} chars)")
            return response_text
            
        except Exception as e:
            logger.error(f"❌ Claude API error: {e}")
            raise
    
    def _parse_ai_response(self, response: str) -> HealingResult:
        """Parse AI response into structured result."""
        logger.info("📝 Parsing AI response...")
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")
            
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            # Convert to FixAction objects
            actions = []
            for action_data in data.get("actions", []):
                action = FixAction(
                    path=action_data["path"],
                    action=action_data["action"],
                    content=action_data.get("content"),
                    reason=action_data.get("reason", "")
                )
                actions.append(action)
            
            result = HealingResult(
                success=data.get("success", False),
                confidence=float(data.get("confidence", 0.0)),
                error_category=data.get("error_category", "unknown"),
                fix_summary=data.get("fix_summary", ""),
                actions=actions,
                reasoning=data.get("reasoning", ""),
                warnings=data.get("warnings", []),
                estimated_time=data.get("estimated_time", "Unknown")
            )
            
            # Validate result
            self._validate_result(result)
            
            logger.info(f"✅ Parsed result: {len(result.actions)} actions, confidence: {result.confidence}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to parse response: {e}")
            logger.debug(f"Raw response: {response[:500]}...")
            
            return HealingResult(
                success=False,
                confidence=0.0,
                error_category="parse_error",
                fix_summary=f"Failed to parse AI response: {str(e)}",
                actions=[],
                reasoning="Could not parse AI response",
                warnings=[f"Parse error: {str(e)}"],
                estimated_time="0 minutes"
            )
    
    def _validate_result(self, result: HealingResult) -> None:
        """Validate the healing result."""
        if result.confidence < 0.0 or result.confidence > 1.0:
            raise ValueError(f"Invalid confidence score: {result.confidence}")
        
        for action in result.actions:
            if action.action not in ["update", "create", "delete"]:
                raise ValueError(f"Invalid action: {action.action}")
            
            if action.path.endswith(".tfstate") or ".terraform/" in action.path:
                raise ValueError(f"Cannot modify protected file: {action.path}")
    
    def export_result(self, result: HealingResult, output_file: str) -> None:
        """Export result to JSON file for GitHub Actions."""
        logger.info(f"💾 Exporting result to {output_file}")
        
        try:
            output_data = asdict(result)
            
            with open(output_file, 'w') as f:
                json.dump(output_data, f, indent=2)
            
            logger.info(f"✅ Result exported successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to export result: {e}")
            raise

def main():
    """Main entry point."""
    logger.info("🚀 Starting AI Healing Agent")
    
    # Get environment variables
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("❌ ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)
    
    error_log_file = os.getenv('ERROR_LOG_FILE', 'error.log')
    repo_path = os.getenv('REPO_PATH', '.')
    terragrunt_path = os.getenv('TERRAGRUNT_PATH', '')
    environment = os.getenv('ENVIRONMENT', 'dev')
    output_file = os.getenv('OUTPUT_FILE', 'healing-result.json')
    
    logger.info(f"📋 Configuration:")
    logger.info(f"  Error log: {error_log_file}")
    logger.info(f"  Repo path: {repo_path}")
    logger.info(f"  Terragrunt path: {terragrunt_path}")
    logger.info(f"  Environment: {environment}")
    logger.info(f"  Output file: {output_file}")
    
    try:
        # Read error logs
        if not os.path.exists(error_log_file):
            logger.error(f"❌ Error log file not found: {error_log_file}")
            sys.exit(1)
        
        with open(error_log_file, 'r') as f:
            error_logs = f.read()
        
        logger.info(f"📄 Read error logs ({len(error_logs)} chars)")
        
        # Create agent and analyze
        agent = TerraformHealingAgent(api_key)
        result = agent.analyze_and_fix(
            error_logs=error_logs,
            repo_path=repo_path,
            terragrunt_path=terragrunt_path,
            environment=environment
        )
        
        # Export result
        agent.export_result(result, output_file)
        
        # Print summary
        if result.success and result.confidence >= 0.7:
            logger.info(f"✅ SUCCESS: {result.fix_summary}")
            logger.info(f"🎯 Confidence: {result.confidence:.2f}")
            logger.info(f"📝 Actions: {len(result.actions)}")
            sys.exit(0)
        else:
            logger.warning(f"⚠️  LOW CONFIDENCE: {result.fix_summary}")
            logger.warning(f"🎯 Confidence: {result.confidence:.2f}")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()