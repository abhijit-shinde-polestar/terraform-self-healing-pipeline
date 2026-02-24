#!/usr/bin/env python3
"""
GitHub Integration for Cross-Repository Self-Healing
Handles branch creation, commits, and workflow triggering in source repos
"""

import os
import sys
import json
import subprocess
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class GitHubIntegration:
    """Handle GitHub operations across repositories"""
    
    def __init__(self, token: str, source_repo: str):
        """
        Initialize GitHub integration
        
        Args:
            token: GitHub Personal Access Token
            source_repo: Source repository in format 'owner/repo'
        """
        self.token = token
        self.source_repo = source_repo
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def clone_repo(self, target_dir: str, ref: str = "main") -> Tuple[bool, str]:
        """Clone the source repository"""
        try:
            clone_url = f"https://{self.token}@github.com/{self.source_repo}.git"
            
            cmd = ["git", "clone", "--depth", "1", "--branch", ref, clone_url, target_dir]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            return True, f"Cloned {self.source_repo} successfully"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to clone: {e.stderr}"
    
    def create_branch(self, repo_dir: str, branch_name: str, base_ref: str = "main") -> Tuple[bool, str]:
        """Create a new branch in the repository"""
        try:
            # Configure git
            subprocess.run(
                ["git", "config", "user.name", "AI Healing Agent"],
                cwd=repo_dir,
                check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "ai-agent@devops.local"],
                cwd=repo_dir,
                check=True
            )
            
            # Create and checkout new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_dir,
                check=True,
                capture_output=True
            )
            
            return True, f"Created branch {branch_name}"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create branch: {e.stderr}"
    
    def apply_changes(self, repo_dir: str, changes: List[Dict]) -> Tuple[bool, str, List[str]]:
        """Apply file changes to the repository"""
        modified_files = []
        
        try:
            for change in changes:
                # Handle both absolute and relative file paths
                file_rel_path = change["file"]
                
                # If the path doesn't start with repo_dir, it's a relative path
                if not file_rel_path.startswith(repo_dir):
                    # Try to find the file in the repo
                    file_path = None
                    for root, dirs, files in os.walk(repo_dir):
                        if os.path.basename(file_rel_path) in files:
                            potential_path = os.path.join(root, os.path.basename(file_rel_path))
                            # Verify this is the right file by checking if it contains the old content
                            if change["action"] == "replace":
                                try:
                                    with open(potential_path, 'r') as f:
                                        if change["old_content"] in f.read():
                                            file_path = potential_path
                                            break
                                except:
                                    continue
                            else:
                                file_path = potential_path
                                break
                    
                    if not file_path:
                        return False, f"Could not find file: {file_rel_path} in {repo_dir}", modified_files
                else:
                    file_path = file_rel_path
                
                action = change["action"]
                
                if action == "replace":
                    success, msg = self._replace_content(
                        file_path,
                        change["old_content"],
                        change["new_content"]
                    )
                elif action == "add":
                    success, msg = self._add_content(file_path, change["new_content"])
                elif action == "remove":
                    success, msg = self._remove_content(file_path, change["old_content"])
                else:
                    return False, f"Unknown action: {action}", []
                
                if not success:
                    return False, msg, modified_files
                
                # Store relative path from repo root for git operations
                modified_files.append(os.path.relpath(file_path, repo_dir))
            
            return True, f"Applied {len(changes)} change(s)", modified_files
        
        except Exception as e:
            return False, f"Error applying changes: {str(e)}", modified_files
    
    def _replace_content(self, file_path: str, old_content: str, new_content: str) -> Tuple[bool, str]:
        """Replace content in a file"""
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        if old_content not in content:
            return False, f"Old content not found in {file_path}"
        
        new_file_content = content.replace(old_content, new_content)
        
        with open(file_path, 'w') as f:
            f.write(new_file_content)
        
        return True, f"Replaced content in {file_path}"
    
    def _add_content(self, file_path: str, new_content: str) -> Tuple[bool, str]:
        """Add content to a file"""
        with open(file_path, 'a') as f:
            f.write(f"\n{new_content}\n")
        
        return True, f"Added content to {file_path}"
    
    def _remove_content(self, file_path: str, content_to_remove: str) -> Tuple[bool, str]:
        """Remove content from a file"""
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        new_content = content.replace(content_to_remove, "")
        
        with open(file_path, 'w') as f:
            f.write(new_content)
        
        return True, f"Removed content from {file_path}"
    
    def commit_and_push(self, repo_dir: str, message: str, files: List[str], branch: str) -> Tuple[bool, str, str]:
        """Commit changes and push to remote"""
        try:
            # Stage files
            for file in files:
                subprocess.run(
                    ["git", "add", file],
                    cwd=repo_dir,
                    check=True
                )
            
            # Commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_dir,
                check=True,
                capture_output=True
            )
            
            # Get commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True
            )
            commit_sha = result.stdout.strip()
            
            # Push
            push_url = f"https://{self.token}@github.com/{self.source_repo}.git"
            subprocess.run(
                ["git", "push", push_url, branch],
                cwd=repo_dir,
                check=True,
                capture_output=True
            )
            
            return True, "Changes committed and pushed", commit_sha
        
        except subprocess.CalledProcessError as e:
            return False, f"Git operation failed: {e.stderr}", ""
    
    def trigger_workflow(self, workflow_id: str, ref: str, inputs: Dict = None) -> Tuple[bool, str]:
        """Trigger a workflow in the source repository"""
        url = f"{self.api_base}/repos/{self.source_repo}/actions/workflows/{workflow_id}/dispatches"
        
        payload = {
            "ref": ref,
            "inputs": inputs or {}
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        
        if response.status_code == 204:
            return True, "Workflow triggered successfully"
        else:
            return False, f"Failed to trigger workflow: {response.text}"
    
    def create_pull_request(self, title: str, head: str, base: str, body: str) -> Tuple[bool, str, int]:
        """Create a pull request"""
        url = f"{self.api_base}/repos/{self.source_repo}/pulls"
        
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        
        if response.status_code == 201:
            pr_number = response.json()["number"]
            return True, f"PR #{pr_number} created", pr_number
        else:
            return False, f"Failed to create PR: {response.text}", 0
    
    def get_workflow_runs(self, workflow_id: str, branch: str, limit: int = 5) -> List[Dict]:
        """Get recent workflow runs for a branch"""
        url = f"{self.api_base}/repos/{self.source_repo}/actions/workflows/{workflow_id}/runs"
        params = {
            "branch": branch,
            "per_page": limit
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code == 200:
            return response.json().get("workflow_runs", [])
        else:
            return []
    
    def wait_for_workflow_completion(self, run_id: int, timeout: int = 600, poll_interval: int = 30) -> Tuple[bool, str]:
        """Wait for a workflow run to complete"""
        url = f"{self.api_base}/repos/{self.source_repo}/actions/runs/{run_id}"
        
        import time
        elapsed = 0
        
        while elapsed < timeout:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                run_data = response.json()
                status = run_data["status"]
                conclusion = run_data.get("conclusion")
                
                if status == "completed":
                    if conclusion == "success":
                        return True, "Workflow completed successfully"
                    else:
                        return False, f"Workflow failed with conclusion: {conclusion}"
            
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        return False, "Workflow timeout"
    
    def comment_on_pr(self, pr_number: int, comment: str) -> Tuple[bool, str]:
        """Add a comment to a pull request"""
        url = f"{self.api_base}/repos/{self.source_repo}/issues/{pr_number}/comments"
        
        payload = {"body": comment}
        
        response = requests.post(url, headers=self.headers, json=payload)
        
        if response.status_code == 201:
            return True, "Comment added"
        else:
            return False, f"Failed to add comment: {response.text}"


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="GitHub integration for self-healing")
    parser.add_argument("--token", required=True, help="GitHub token")
    parser.add_argument("--repo", required=True, help="Source repository (owner/repo)")
    parser.add_argument("--action", required=True, 
                       choices=["apply-fix", "trigger-workflow", "check-workflow", "create-pr"])
    parser.add_argument("--fix-file", help="Path to fix JSON file")
    parser.add_argument("--source-dir", help="Path to source repository")
    parser.add_argument("--branch-name", help="Branch name")
    parser.add_argument("--base-branch", help="Base branch name")
    parser.add_argument("--commit-message", help="Commit message")
    parser.add_argument("--workflow", help="Workflow ID or filename")
    parser.add_argument("--ref", help="Git reference")
    parser.add_argument("--inputs", help="Workflow inputs as JSON string")
    parser.add_argument("--branch", help="Branch to check")
    parser.add_argument("--head", help="PR head branch")
    parser.add_argument("--base", help="PR base branch")
    parser.add_argument("--title", help="PR title")
    parser.add_argument("--body", help="PR body")
    parser.add_argument("--output", help="Output file for results")
    
    args = parser.parse_args()
    
    gh = GitHubIntegration(args.token, args.repo)
    result = {}
    
    try:
        if args.action == "apply-fix":
            # Load fix file
            with open(args.fix_file, 'r') as f:
                fix_data = json.load(f)
            
            if not fix_data.get("success"):
                result = {"success": False, "message": "Fix data indicates failure"}
            else:
                # Create branch
                success, msg = gh.create_branch(args.source_dir, args.branch_name, args.base_branch)
                if not success:
                    result = {"success": False, "message": msg}
                else:
                    # Apply changes
                    changes = fix_data.get("fix", {}).get("changes", [])
                    success, msg, files = gh.apply_changes(args.source_dir, changes)
                    
                    if not success:
                        result = {"success": False, "message": msg}
                    else:
                        # Commit and push
                        success, msg, commit_sha = gh.commit_and_push(
                            args.source_dir, args.commit_message, files, args.branch_name
                        )
                        
                        if success:
                            result = {
                                "success": True,
                                "message": msg,
                                "commit_sha": commit_sha,
                                "files_modified": files
                            }
                        else:
                            result = {"success": False, "message": msg}
        
        elif args.action == "trigger-workflow":
            inputs = json.loads(args.inputs) if args.inputs else {}
            success, msg = gh.trigger_workflow(args.workflow, args.ref, inputs)
            result = {"success": success, "message": msg}
        
        elif args.action == "check-workflow":
            runs = gh.get_workflow_runs(args.workflow, args.branch, limit=1)
            if runs:
                run = runs[0]
                result = {
                    "success": run["conclusion"] == "success",
                    "status": run["status"],
                    "conclusion": run.get("conclusion"),
                    "run_id": run["id"]
                }
            else:
                result = {"success": False, "message": "No workflow runs found"}
        
        elif args.action == "create-pr":
            success, msg, pr_number = gh.create_pull_request(
                args.title, args.head, args.base, args.body
            )
            result = {"success": success, "message": msg, "pr_number": pr_number}
        
        # Write output
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
        
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success", False) else 1)
    
    except Exception as e:
        error_result = {"success": False, "message": str(e)}
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(error_result, f, indent=2)
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
