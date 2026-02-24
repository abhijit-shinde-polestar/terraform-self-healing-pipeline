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
                file_path = os.path.join(repo_dir, change["file"])
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
                
                modified_files.append(change["file"])
            
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
    """Main entry point for testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description="GitHub integration for self-healing")
    parser.add_argument("--token", required=True, help="GitHub token")
    parser.add_argument("--repo", required=True, help="Source repository (owner/repo)")
    parser.add_argument("--action", required=True, choices=["clone", "create-branch", "trigger-workflow"])
    parser.add_argument("--ref", default="main", help="Git reference")
    parser.add_argument("--branch", help="Branch name")
    parser.add_argument("--workflow", help="Workflow ID or filename")
    
    args = parser.parse_args()
    
    gh = GitHubIntegration(args.token, args.repo)
    
    if args.action == "clone":
        success, msg = gh.clone_repo("/tmp/test-clone", args.ref)
        print(msg)
        sys.exit(0 if success else 1)
    
    elif args.action == "create-branch":
        if not args.branch:
            print("--branch required")
            sys.exit(1)
        success, msg = gh.create_branch("/tmp/test-clone", args.branch)
        print(msg)
        sys.exit(0 if success else 1)
    
    elif args.action == "trigger-workflow":
        if not args.workflow:
            print("--workflow required")
            sys.exit(1)
        success, msg = gh.trigger_workflow(args.workflow, args.ref)
        print(msg)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
