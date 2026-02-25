# Self-Healing Pipeline Flow Documentation

## Overview

The self-healing pipeline automatically detects, analyzes, and fixes Terraform/Terragrunt deployment failures using AI (Claude Sonnet 4.5). It commits fixes to the **same branch** where the failure occurred and waits for the deployment workflow to complete before retrying.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    elz-devops-tools Repository                   │
│                                                                   │
│  Feature Branch (feature/my-feature)                             │
│  ├─ Push commit                                                  │
│  ├─ Triggers: feature-validation.yaml                            │
│  │  ├─ Format Check                                              │
│  │  ├─ Terragrunt Plan                                           │
│  │  └─ If FAIL → Upload error logs + Trigger self-healing       │
│  │                                                                │
│  Develop Branch (develop)                                        │
│  ├─ Merge from feature/*                                         │
│  ├─ Triggers: deploy-to-dev.yaml                                 │
│  │  ├─ Job 1: plan-dev                                           │
│  │  │  ├─ Format Check                                           │
│  │  │  ├─ Terragrunt Plan                                        │
│  │  │  └─ If FAIL → Upload error logs + Trigger self-healing    │
│  │  └─ Job 2: apply-dev (runs if plan-dev succeeds)             │
│  │     ├─ Terragrunt Apply                                       │
│  │     └─ If FAIL → Upload error logs + Trigger self-healing    │
│  │                                                                │
│  Release Branch (release/vX.Y.Z) → PR to main                    │
│  ├─ Triggers: promote-to-test.yaml                               │
│  │  ├─ Job 1: plan-test                                          │
│  │  │  └─ Terragrunt Plan                                        │
│  │  └─ Job 2: apply-test (runs if plan-test succeeds)           │
│  │     └─ Terragrunt Apply                                       │
│  │     └─ No self-healing (manual intervention required)         │
│  │                                                                │
│  Main Branch (main) - after release merge                        │
│  ├─ Triggers: promote-to-prod.yaml                               │
│  │  ├─ Job 1: plan-prod                                          │
│  │  │  └─ Terragrunt Plan                                        │
│  │  └─ Job 2: apply-prod (manual approval required)             │
│  │     └─ Terragrunt Apply                                       │
│  │     └─ No self-healing (manual intervention required)         │
└───────────────────────────────────────────────────────────────────┘
                              │
                              │ repository_dispatch event
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           terraform-self-healing-pipeline Repository             │
│                                                                   │
│  Workflow: self-healing-agent.yaml                               │
│  ├─ Triggered by: repository_dispatch (heal-deployment)          │
│  ├─ Downloads error logs from source repo                        │
│  ├─ Clones source repo on the SAME branch                        │
│  │                                                                │
│  └─ Retry Loop (max 5 attempts for dev):                         │
│     ├─ Attempt 1:                                                │
│     │  ├─ AI analyzes error logs                                 │
│     │  ├─ Generates fix with confidence score                    │
│     │  ├─ Applies fix to source repo files                       │
│     │  ├─ Commits to SAME branch (e.g., feature/my-feature)      │
│     │  ├─ Push triggers source workflow automatically            │
│     │  ├─ Waits 45s for workflow to start                        │
│     │  ├─ Polls every 30s (max 15 min) for completion            │
│     │  ├─ Checks if all jobs (plan + apply) succeeded            │
│     │  └─ If SUCCESS → Exit ✅                                    │
│     │     If FAILURE → Download new error logs                   │
│     │                                                             │
│     ├─ Attempt 2:                                                │
│     │  ├─ AI analyzes NEW error logs                             │
│     │  ├─ Generates different fix                                │
│     │  ├─ Commits to SAME branch                                 │
│     │  ├─ Push triggers workflow again                           │
│     │  ├─ Waits and polls for completion                         │
│     │  └─ If SUCCESS → Exit ✅                                    │
│     │     If FAILURE → Continue...                               │
│     │                                                             │
│     └─ ... (up to 5 attempts)                                    │
│                                                                   │
│  Result:                                                          │
│  ├─ Success: Branch is fixed and deployment verified             │
│  └─ Failure: Manual intervention required after 5 attempts       │
└───────────────────────────────────────────────────────────────────┘
```

---

## Detailed Flow

### 1. Failure Detection

**Trigger Conditions:**
- Format check fails
- Terragrunt plan fails
- Terragrunt apply fails

**Actions:**
1. Upload error logs as artifact
2. Trigger self-healing via `repository_dispatch` event
3. Pass metadata:
   - Source repository
   - Source branch/ref
   - Artifact name
   - Workload path
   - Environment (dev/test/prod)
   - Confidence threshold
   - Max retry attempts

---

### 2. Self-Healing Initialization

**Self-Healing Agent Workflow:**

```yaml
on:
  repository_dispatch:
    types: [heal-deployment]
```

**Steps:**
1. **Download Error Logs**
   - Uses GitHub API to download artifact from source repo
   - Extracts error logs for AI analysis

2. **Clone Source Repository**
   - Clones on the **exact same branch** where failure occurred
   - Examples:
     - `feature/add-new-service` (feature branch)
     - `develop` (dev deployment)
     - `release/v1.2.0` (test deployment)

3. **Extract Branch Name**
   - Handles both regular refs (`refs/heads/develop`)
   - And PR refs (`refs/pull/123/merge`)

---

### 3. Retry Loop with AI Analysis

**For each attempt (1 to max_attempts):**

#### Step 1: AI Analysis
```bash
python .github/scripts/ai-healing-agent.py \
  --error-log ../error-logs/terragrunt-error.log \
  --context-dir ../source-repo/workloads/my-service \
  --output fix-result.json \
  --min-confidence 0.7
```

**AI Output:**
```json
{
  "success": true,
  "confidence": 0.85,
  "fix": {
    "category": "configuration_error",
    "root_cause": "Missing required variable",
    "changes": [
      {
        "file": "workloads/my-service/dev.hcl",
        "action": "replace",
        "old_content": "# vpc_id = \"vpc-123\"",
        "new_content": "vpc_id = \"vpc-abc123\""
      }
    ]
  }
}
```

#### Step 2: Apply Fix to Same Branch
```bash
python .github/scripts/github-integration.py \
  --action apply-fix \
  --fix-file fix-result.json \
  --source-dir ../source-repo \
  --branch-name feature/my-feature \
  --commit-message "🤖 Auto-fix: Deployment error (attempt 1)"
```

**Git Operations:**
```bash
cd source-repo
git add workloads/my-service/dev.hcl
git commit -m "🤖 Auto-fix: Deployment error (attempt 1)"
git push origin feature/my-feature
```

#### Step 3: Wait for Source Workflow

**Automatic Trigger:**
- Push to branch automatically triggers the source workflow
- No manual workflow_dispatch needed

**Polling Logic:**
```bash
# Wait 45 seconds for workflow to start
sleep 45

# Poll every 30 seconds for up to 15 minutes
for i in {1..30}; do
  check-latest-workflow --branch feature/my-feature
  
  if workflow.status == "completed":
    if workflow.conclusion == "success":
      echo "✅ All jobs succeeded!"
      exit 0
    else:
      echo "❌ Jobs failed, downloading new errors..."
      break
  fi
  
  sleep 30
done
```

#### Step 4: Download New Error Logs (if failed)
```bash
# Get the failed run ID
FAILED_RUN_ID=$(jq -r '.run_id' workflow-status.json)

# Download new error artifact
curl -H "Authorization: token $GH_PAT" \
  "https://api.github.com/repos/elz-devops-tools/actions/runs/$FAILED_RUN_ID/artifacts" \
  | jq -r '.artifacts[] | select(.name | contains("error-logs")) | .archive_download_url'

# Extract new logs
unzip artifact.zip -d error-logs/
```

#### Step 5: Retry with New Analysis
- AI analyzes **new** error logs
- May generate a **different** fix
- Commits to **same branch** again
- Process repeats

---

## Key Features

### ✅ Same Branch Commits

**Why?**
- Maintains Git history on the working branch
- No orphaned fix branches
- Clean PR workflow
- Automatic workflow re-triggering

**Example:**
```
feature/add-monitoring
├─ Initial commit (fails)
├─ 🤖 Auto-fix attempt 1 (fails)
├─ 🤖 Auto-fix attempt 2 (succeeds)
└─ Merge to develop ✅
```

### ✅ Workflow Completion Polling

**Implementation:**
```python
def check_latest_workflow(branch):
    """Get the most recent workflow run for a branch"""
    url = f"/repos/{repo}/actions/runs"
    params = {
        "branch": branch,
        "per_page": 5,
        "event": "push"
    }
    
    runs = api_get(url, params)
    latest_run = runs[0]
    
    return {
        "status": latest_run["status"],        # queued, in_progress, completed
        "conclusion": latest_run["conclusion"], # success, failure, cancelled
        "run_id": latest_run["id"],
        "html_url": latest_run["html_url"]
    }
```

**Handles Job-Based Workflows:**
- Waits for **all jobs** (plan + apply) to complete
- Checks overall workflow conclusion
- Downloads errors from the specific failed job

### ✅ Environment-Specific Configuration

| Environment | Self-Healing | Confidence | Max Attempts | Timeout |
|-------------|--------------|------------|--------------|---------|
| **Feature** | ✅ Enabled   | 70%        | 5            | 15 min  |
| **DEV**     | ✅ Enabled   | 70%        | 5            | 15 min  |
| **TEST**    | ❌ Disabled  | -          | -            | -       |
| **PROD**    | ❌ Disabled  | -          | -            | -       |

---

## Error Handling

### Scenario 1: AI Confidence Too Low
```
Attempt 1: AI confidence = 0.65 (below 0.7 threshold)
Action: Skip fix, exit with failure
Result: Manual intervention required
```

### Scenario 2: Workflow Timeout
```
Attempt 1: Fix applied, workflow running for 15+ minutes
Action: Mark as timeout, try next attempt
Result: New fix applied with fresh analysis
```

### Scenario 3: No Workflow Detected
```
Attempt 1: Fix pushed, but no workflow run found after 45s
Action: Continue to next attempt
Possible Cause: Workflow may be disabled or branch protection
```

### Scenario 4: Max Attempts Reached
```
Attempt 5: Still failing after 5 fixes
Action: Exit with failure status
Result: Create GitHub issue or notify team (future enhancement)
```

---

## Workflow Interactions

### Feature Branch → Self-Healing
```
1. Developer pushes to feature/new-feature
2. feature-validation.yaml runs
3. Plan fails with error
4. Uploads error-logs artifact
5. Triggers self-healing
6. Self-healing:
   ├─ Downloads error logs
   ├─ Clones feature/new-feature
   ├─ AI generates fix
   ├─ Commits to feature/new-feature
   ├─ Push triggers feature-validation.yaml again
   ├─ Waits for plan to succeed
   └─ Success! Developer can now merge to develop
```

### Develop Branch → Self-Healing
```
1. Feature merged to develop
2. deploy-to-dev.yaml runs
3. Plan job succeeds
4. Apply job fails
5. Uploads apply-error-logs artifact
6. Triggers self-healing
7. Self-healing:
   ├─ Downloads apply error logs
   ├─ Clones develop branch
   ├─ AI analyzes apply failure
   ├─ Commits fix to develop
   ├─ Push triggers deploy-to-dev.yaml again
   ├─ Both plan and apply jobs run
   ├─ Waits for both jobs to succeed
   └─ Success! DEV environment updated
```

---

## Configuration

### Repository Variables (elz-devops-tools)

```yaml
ENABLE_SELF_HEALING: 'true'
PS_DEV_WORKLOAD_AUTOMATION_IAM_ROLE_ARN: 'arn:aws:iam::...'
PS_TEST_WORKLOAD_AUTOMATION_IAM_ROLE_ARN: 'arn:aws:iam::...'
PS_PROD_WORKLOAD_AUTOMATION_IAM_ROLE_ARN: 'arn:aws:iam::...'
```

### Repository Secrets (both repos)

```yaml
GH_PAT: 'ghp_...'  # GitHub Personal Access Token with repo scope
ANTHROPIC_API_KEY: 'sk-ant-...'  # Claude API key
```

### Trigger Payload

```json
{
  "event_type": "heal-deployment",
  "client_payload": {
    "source_repo": "org/elz-devops-tools",
    "source_ref": "refs/heads/feature/my-feature",
    "artifact_name": "deployment-error-logs-dev-123",
    "workload_path": "workloads/my-service/dev.hcl",
    "environment": "dev",
    "min_confidence": "0.7",
    "run_id": "123456789",
    "failure_type": "apply",
    "workflow_name": "deploy-to-dev.yaml",
    "max_attempts": 5
  }
}
```

---

## Monitoring and Debugging

### Check Self-Healing Status

**GitHub Actions UI:**
```
terraform-self-healing-pipeline
└─ Actions
   └─ Self-Healing Agent
      └─ Run #123
         ├─ Attempt 1: ❌ Failed
         ├─ Attempt 2: ❌ Failed
         └─ Attempt 3: ✅ Success
```

### View Healing Results

**Artifacts:**
- `healing-results-{run_number}`
  - `fix-result.json` - AI analysis and fix
  - `apply-result.json` - Git commit details
  - `workflow-status.json` - Source workflow status

### Common Issues

**Issue: Self-healing not triggering**
```
Check:
1. ENABLE_SELF_HEALING = 'true'
2. GH_PAT has repo scope
3. Error logs uploaded successfully
4. Repository dispatch event sent
```

**Issue: Workflow not detected**
```
Check:
1. Branch name matches exactly
2. Workflow file exists in .github/workflows/
3. Workflow is enabled (not disabled)
4. Branch protection allows pushes
```

**Issue: Fix not applied**
```
Check:
1. AI confidence >= threshold
2. File paths are correct
3. Old content matches exactly
4. Git credentials are valid
```

---

## Future Enhancements

- [ ] Slack/Teams notifications on success/failure
- [ ] GitHub issue creation after max attempts
- [ ] Metrics dashboard (success rate, avg attempts, etc.)
- [ ] Support for multiple concurrent fixes
- [ ] Learning from past fixes (fix database)
- [ ] Dry-run mode for testing
- [ ] Custom fix templates per error type

---

## Security Considerations

✅ **GitHub PAT Scope:** Minimum required: `repo` (read/write)  
✅ **API Keys:** Stored as encrypted secrets  
✅ **Branch Protection:** Self-healing respects branch protection rules  
✅ **Audit Trail:** All commits signed by "AI Healing Agent"  
✅ **Confidence Threshold:** Prevents low-confidence fixes  
✅ **Max Attempts:** Prevents infinite loops  

---

## Summary

The self-healing pipeline provides **intelligent, automated recovery** from Terraform/Terragrunt failures by:

1. ✅ Committing fixes to the **same branch** where failures occur
2. ✅ Waiting for source workflows to **complete** before retrying
3. ✅ Downloading **new error logs** after each failed attempt
4. ✅ Supporting **job-based workflows** (plan + apply)
5. ✅ Providing **environment-specific** configuration
6. ✅ Maintaining **clean Git history** without orphaned branches

This enables rapid iteration in development while maintaining safety in production.
