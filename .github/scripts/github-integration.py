#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

class GitHubRateLimitError(Exception):
    """Custom exception for rate limit errors"""
    def __init__(self, message: str, reset_time: Optional[int] = None):
        self.message = message
        self.reset_time = reset_time
        super().__init__(self.message)

class GitHubIntegration:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'self-healing-pipeline/1.0'
        })
        
    def _make_request(self, method: str, url: str, data: Optional[Dict] = None, 
                     max_retries: int = 3) -> requests.Response:
        """Make GitHub API request with rate limit handling and retries"""
        for attempt in range(max_retries + 1):
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, params=data)
                elif method.upper() == 'POST':
                    response = self.session.post(url, json=data)
                elif method.upper() == 'PUT':
                    response = self.session.put(url, json=data)
                elif method.upper() == 'DELETE':
                    response = self.session.delete(url)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Check for rate limiting
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    current_time = int(time.time())
                    wait_time = max(reset_time - current_time, 60)  # Wait at least 60 seconds
                    
                    print(f"⚠️ GitHub API rate limit hit. Attempt {attempt + 1}/{max_retries + 1}")
                    print(f"Rate limit resets at: {datetime.fromtimestamp(reset_time, timezone.utc)}")
                    
                    if attempt < max_retries:
                        print(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise GitHubRateLimitError(
                            f"GitHub API rate limit exceeded. Reset time: {reset_time}",
                            reset_time
                        )
                
                # Check for secondary rate limiting (abuse detection)
                elif response.status_code == 403 and 'abuse' in response.text.lower():
                    wait_time = min(60 * (2 ** attempt), 300)  # Exponential backoff, max 5 minutes
                    
                    print(f"⚠️ GitHub abuse detection triggered. Attempt {attempt + 1}/{max_retries + 1}")
                    
                    if attempt < max_retries:
                        print(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise GitHubRateLimitError(
                            "GitHub abuse detection triggered. Please wait before making more requests."
                        )
                
                # Check rate limit headers and warn if approaching limit
                remaining = int(response.headers.get('X-RateLimit-Remaining', 1))
                if remaining < 100:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    reset_datetime = datetime.fromtimestamp(reset_time, timezone.utc)
                    print(f"⚠️ GitHub API rate limit warning: {remaining} requests remaining")
                    print(f"Rate limit resets at: {reset_datetime}")
                
                # For other 4xx/5xx errors, don't retry immediately
                if response.status_code >= 400:
                    if attempt < max_retries and response.status_code >= 500:
                        wait_time = min(10 * (2 ** attempt), 60)  # Exponential backoff for server errors
                        print(f"⚠️ Server error {response.status_code}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()
                
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    wait_time = min(5 * (2 ** attempt), 30)  # Exponential backoff
                    print(f"⚠️ Request failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
        
        raise Exception(f"Failed to complete request after {max_retries + 1} attempts")
    
    def download_artifact(self, repo: str, run_id: str, artifact_name: str, download_path: str) -> bool:
        """Download artifact from GitHub Actions run"""
        try:
            print(f"📥 Downloading artifact '{artifact_name}' from run {run_id}")
            
            # List artifacts for the run
            artifacts_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts"
            response = self._make_request('GET', artifacts_url)
            artifacts = response.json()
            
            # Find the specific artifact
            artifact = None
            for art in artifacts['artifacts']:
                if art['name'] == artifact_name:
                    artifact = art
                    break
            
            if not artifact:
                print(f"❌ Artifact '{artifact_name}' not found in run {run_id}")
                return False
            
            # Download the artifact
            download_url = artifact['archive_download_url']
            response = self._make_request('GET', download_url)
            
            # Save to file
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            with open(download_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Artifact downloaded to: {download_path}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to download artifact: {e}")
            return False
    
    def clone_repository(self, repo: str, ref: str, clone_path: str) -> bool:
        """Clone repository to local path"""
        try:
            if os.path.exists(clone_path):
                subprocess.run(['rm', '-rf', clone_path], check=True)
            
            clone_url = f"https://{self.token}@github.com/{repo}.git"
            cmd = ['git', 'clone', '--branch', ref.replace('refs/heads/', ''), clone_url, clone_path]
            
            print(f"📦 Cloning {repo}@{ref} to {clone_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                print(f"✅ Repository cloned successfully")
                return True
            else:
                print(f"❌ Clone failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"❌ Clone timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"❌ Clone failed: {e}")
            return False
    
    def create_branch(self, repo_path: str, branch_name: str, base_branch: str = None) -> bool:
        """Create and checkout a new branch"""
        try:
            os.chdir(repo_path)
            
            if base_branch:
                subprocess.run(['git', 'checkout', base_branch], check=True)
            
            result = subprocess.run(['git', 'checkout', '-b', branch_name], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ Created and checked out branch: {branch_name}")
                return True
            else:
                print(f"❌ Failed to create branch: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to create branch: {e}")
            return False
    
    def commit_and_push(self, repo_path: str, message: str, branch: str) -> bool:
        """Commit changes and push to remote"""
        try:
            os.chdir(repo_path)
            
            # Add all changes
            subprocess.run(['git', 'add', '.'], check=True)
            
            # Check if there are changes to commit
            result = subprocess.run(['git', 'diff', '--cached', '--quiet'], 
                                  capture_output=True)
            if result.returncode == 0:
                print("ℹ️ No changes to commit")
                return True
            
            # Commit changes
            subprocess.run(['git', 'commit', '-m', message], check=True)
            
            # Push with rate limit awareness
            max_push_retries = 3
            for attempt in range(max_push_retries):
                try:
                    subprocess.run(['git', 'push', 'origin', branch], check=True, timeout=300)
                    print(f"✅ Committed and pushed to {branch}")
                    return True
                except subprocess.TimeoutExpired:
                    if attempt < max_push_retries - 1:
                        print(f"⚠️ Push timed out. Retrying... ({attempt + 1}/{max_push_retries})")
                        time.sleep(10)
                        continue
                    else:
                        print(f"❌ Push failed after {max_push_retries} attempts")
                        return False
                except subprocess.CalledProcessError as e:
                    if 'rate limit' in str(e).lower() and attempt < max_push_retries - 1:
                        print(f"⚠️ Git push rate limited. Waiting 60s... ({attempt + 1}/{max_push_retries})")
                        time.sleep(60)
                        continue
                    else:
                        print(f"❌ Push failed: {e}")
                        return False
                        
        except Exception as e:
            print(f"❌ Commit and push failed: {e}")
            return False
    
    def trigger_workflow(self, repo: str, workflow: str, ref: str, inputs: Dict[str, Any] = None) -> Optional[str]:
        """Trigger a workflow in the repository"""
        try:
            url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
            
            data = {
                'ref': ref.replace('refs/heads/', ''),
                'inputs': inputs or {}
            }
            
            print(f"🚀 Triggering workflow '{workflow}' on {ref}")
            response = self._make_request('POST', url, data)
            
            if response.status_code == 204:
                print(f"✅ Workflow triggered successfully")
                
                # Wait a bit for the run to start, then find it
                time.sleep(10)
                return self._find_latest_run(repo, workflow, ref.replace('refs/heads/', ''))
            else:
                print(f"❌ Failed to trigger workflow: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Failed to trigger workflow: {e}")
            return None
    
    def _find_latest_run(self, repo: str, workflow: str, branch: str) -> Optional[str]:
        """Find the latest workflow run for a specific branch"""
        try:
            url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs"
            params = {'branch': branch, 'per_page': 10}
            
            response = self._make_request('GET', url, params)
            runs = response.json()
            
            if runs['workflow_runs']:
                latest_run = runs['workflow_runs'][0]
                return str(latest_run['id'])
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to find latest run: {e}")
            return None
    
    def monitor_workflow_run(self, repo: str, run_id: str, timeout_minutes: int = 15) -> Dict[str, Any]:
        """Monitor workflow run until completion"""
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        print(f"👀 Monitoring workflow run {run_id} (timeout: {timeout_minutes}min)")
        
        while time.time() - start_time < timeout_seconds:
            try:
                url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
                response = self._make_request('GET', url)
                run_data = response.json()
                
                status = run_data['status']
                conclusion = run_data.get('conclusion')
                
                print(f"⏳ Status: {status}, Conclusion: {conclusion or 'pending'}")
                
                if status == 'completed':
                    return {
                        'success': conclusion == 'success',
                        'status': status,
                        'conclusion': conclusion,
                        'run_data': run_data
                    }
                
                # Check rate limit and adjust sleep time accordingly
                remaining = int(response.headers.get('X-RateLimit-Remaining', 1000))
                if remaining < 10:
                    sleep_time = 60  # Sleep longer when approaching rate limit
                else:
                    sleep_time = 30
                    
                time.sleep(sleep_time)
                
            except GitHubRateLimitError as e:
                print(f"⚠️ Rate limited while monitoring. Waiting...")
                if e.reset_time:
                    wait_time = max(e.reset_time - int(time.time()), 60)
                    time.sleep(wait_time)
                else:
                    time.sleep(60)
                continue
            except Exception as e:
                print(f"❌ Error monitoring workflow: {e}")
                time.sleep(30)
                continue
        
        print(f"⏰ Monitoring timed out after {timeout_minutes} minutes")
        return {'success': False, 'status': 'timeout', 'conclusion': 'timeout'}
    
    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str) -> Optional[Dict]:
        """Create a pull request"""
        try:
            url = f"https://api.github.com/repos/{repo}/pulls"
            
            data = {
                'title': title,
                'head': head,
                'base': base,
                'body': body
            }
            
            print(f"📋 Creating PR: {head} → {base}")
            response = self._make_request('POST', url, data)
            
            if response.status_code == 201:
                pr_data = response.json()
                print(f"✅ PR created: {pr_data['html_url']}")
                return pr_data
            else:
                print(f"❌ Failed to create PR: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Failed to create PR: {e}")
            return None

def main():
    """Main function for testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='GitHub Integration Script')
    parser.add_argument('--token', required=True, help='GitHub token')
    parser.add_argument('--repo', required=True, help='Repository (owner/name)')
    parser.add_argument('--action', required=True, choices=[
        'download-artifact', 'clone', 'trigger-workflow', 'monitor-run', 'create-pr'
    ])
    
    args = parser.parse_args()
    
    gh = GitHubIntegration(args.token)
    
    if args.action == 'download-artifact':
        # Example usage
        success = gh.download_artifact(args.repo, '123456', 'error-logs', './error-logs.zip')
        sys.exit(0 if success else 1)
    
    print("GitHub Integration Script ready")

if __name__ == '__main__':
    main()