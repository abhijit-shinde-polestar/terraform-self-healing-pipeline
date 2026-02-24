# Integration Guide: Self-Healing Pipeline

This guide explains how to integrate the self-healing pipeline with your Terraform/Terragrunt application repositories.

## 🎯 Overview

The self-healing pipeline works as a **separate repository** that gets triggered when deployments fail in your application repositories. It:

1. Receives failure notification via `repository_dispatch`
2. Downloads error logs from the failed deployment
3. Clones the source repository
4. Analyzes errors with AI
5. Creates a fix branch in the source repo
6. Commits fixes and pushes
7. Triggers redeployment
8. Monitors and retries until success

## 🔧 Setup for Application Repositories

### Step 1: Add GitHub Secrets

In your **application repository** (e.g., `elz-devops-tools`), add these secrets:

```
Settings → Secrets and variables → Actions → New repository secret

ANTHROPIC_API_KEY    # Claude API key from console.anthropic.com
GH_PAT               # GitHub Personal Access Token (see below)
```

### Step 2: Create GitHub Personal Access Token

The `GH_PAT` needs these permissions:
- `repo` (full control)
- `workflow` (update workflows)

Create it at: https://github.com/settings/tokens/new

### Step 3: Update Your Deployment Workflow

Add the self-healing trigger to your existing deployment workflow:

```yaml
# .github/workflows/terragrunt-deployment.yaml

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      # ... your existing deployment steps ...
      
      - name: Terragrunt Deployment
        id: deploy
        continue-on-error: true
        run: |
          terragrunt apply --auto-approve 2>&1 | tee error.log
          echo "exit_code=$?" >> $GITHUB_OUTPUT
      
      - name: Upload Error Logs
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: deployment-error-logs-${{ github.run_number }}
          path: error.log
          retention-days: 7
      
      - name: Trigger Self-Healing Pipeline
        if: |
          failure() && 
          steps.deploy.outcome == 'failure' &&
          github.event.inputs.triggered_by != 'self-healing-agent'
        env:
          GH_PAT: ${{ secrets.GH_PAT }}
        run: |
          curl -X POST \
            -H "Authorization: token ${GH_PAT}" \
            -H "Accept: application/vnd.github.v3+json" \
            https://api.github.com/repos/your-org/terraform-self-healing-pipeline/dispatches \
            -d '{
              "event_type": "heal-deployment",
              "client_payload": {
                "source_repo": "${{ github.repository }}",
                "source_ref": "${{ github.ref }}",
                "error_log_artifact": "deployment-error-logs-${{ github.run_number }}",
                "terragrunt_path": "path/to/your/terragrunt",
                "environment": "dev",
                "workflow_to_trigger": "terragrunt-deployment.yaml",
                "max_attempts": 5,
                "min_confidence": 0.7,
                "run_id": "${{ github.run_id }}"
              }
            }'
```

### Step 4: Add Workflow Dispatch Input

To prevent infinite loops, add this input to your workflow:

```yaml
on:
  workflow_dispatch:
    inputs:
      triggered_by:
        description: 'Triggered by (internal use)'
        required: false
        type: string
        default: 'manual'
```

## 🔄 How It Works

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Application Repo (elz-devops-tools)                        │
│                                                              │
│  1. Deployment fails                                        │
│  2. Upload error logs as artifact                           │
│  3. Trigger repository_dispatch to healing pipeline         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Self-Healing Pipeline Repo                                 │
│                                                              │
│  4. Receive repository_dispatch event                       │
│  5. Download error logs from app repo                       │
│  6. Clone app repo                                          │
│  7. Analyze error with AI                                   │
│  8. Generate fix                                            │
│  9. Create branch: auto-fix/env-timestamp-attempt-N         │
│  10. Apply fixes to files                                   │
│  11. Commit and push to app repo                            │
│  12. Trigger app repo workflow via workflow_dispatch        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Application Repo (elz-devops-tools)                        │
│                                                              │
│  13. Workflow triggered on new branch                       │
│  14. Run deployment with fixes                              │
│  15. If success: Create PR for review                       │
│  16. If failure: Repeat from step 7 (max 5 attempts)        │
└─────────────────────────────────────────────────────────────┘
```

### Example Execution

```
App Repo: elz-devops-tools
Branch: develop
Deployment: FAILED ❌

↓ (triggers healing pipeline)

Healing Pipeline Repo
Attempt 1/5:
  - Downloads error log
  - AI Analysis: Provider version mismatch (95% confidence)
  - Creates branch: auto-fix/dev-20260224-233015-attempt-1
  - Fixes: provision/hoppscotch/versions.tf
  - Commits: "🤖 Auto-fix: provider_version (attempt 1)"
  - Pushes to elz-devops-tools
  - Triggers deployment on new branch

↓ (app repo redeploys)

App Repo: elz-devops-tools
Branch: auto-fix/dev-20260224-233015-attempt-1
Deployment: SUCCESS ✅

↓

Healing Pipeline:
  - Creates PR: "🤖 Auto-fix: dev deployment (attempt 1)"
  - PR ready for review and merge
```

## 📋 Configuration Options

### Client Payload Parameters

When triggering the healing pipeline, you can customize:

```json
{
  "event_type": "heal-deployment",
  "client_payload": {
    "source_repo": "owner/repo",           // Required
    "source_ref": "refs/heads/main",       // Required
    "error_log_artifact": "error-logs",    // Required
    "terragrunt_path": "workloads/app",    // Required
    "environment": "dev",                  // Required
    "workflow_to_trigger": "deploy.yaml",  // Optional (default: terragrunt-deployment.yaml)
    "max_attempts": 5,                     // Optional (default: 5)
    "min_confidence": 0.7,                 // Optional (default: 0.7)
    "run_id": "1234567890"                 // Required (for artifact download)
  }
}
```

### Environment-Specific Settings

Adjust confidence thresholds per environment:

```yaml
# Dev environment - more permissive
"min_confidence": 0.6
"max_attempts": 5

# Test environment - moderate
"min_confidence": 0.7
"max_attempts": 5

# Production - strict (or disabled)
"min_confidence": 0.9
"max_attempts": 3
```

## 🛡️ Safety Features

### 1. Branch Isolation
All fixes are created in separate branches:
- Pattern: `auto-fix/{environment}-{timestamp}-attempt-{N}`
- Never modifies main/develop directly
- Requires PR review before merge

### 2. Infinite Loop Prevention
- `triggered_by` input prevents self-triggering
- Max attempts limit (default: 5)
- Exponential backoff between attempts

### 3. File Protection
- Never modifies `.tfstate` files
- Never modifies `.terraform.lock.hcl`
- Blocks changes to secrets directories

### 4. Confidence Thresholds
- AI must be confident (70%+ default)
- Low confidence fixes are rejected
- Manual intervention required for uncertain cases

## 🧪 Testing the Integration

### Test 1: Simulate a Failure

```bash
# In your app repo, introduce a known error
cd elz-devops-tools/provision/hoppscotch

# Change provider version to cause mismatch
echo 'version = "~> 5.80.0"' >> versions.tf

# Commit and push
git add versions.tf
git commit -m "Test: Introduce provider version error"
git push origin develop
```

Watch the workflow:
1. Deployment fails
2. Self-healing pipeline is triggered
3. AI analyzes and fixes the error
4. New branch created with fix
5. Deployment retried and succeeds
6. PR created for review

### Test 2: Manual Trigger

```bash
# Trigger healing pipeline manually
curl -X POST \
  -H "Authorization: token YOUR_GH_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/your-org/terraform-self-healing-pipeline/dispatches \
  -d '{
    "event_type": "heal-deployment",
    "client_payload": {
      "source_repo": "your-org/elz-devops-tools",
      "source_ref": "refs/heads/develop",
      "error_log_artifact": "deployment-error-logs-123",
      "terragrunt_path": "workloads/polestar/hoppscotch",
      "environment": "dev",
      "run_id": "1234567890"
    }
  }'
```

## 📊 Monitoring

### View Healing Attempts

1. Go to healing pipeline repo
2. Actions → Self-Healing Agent
3. View workflow runs
4. Download artifacts for detailed logs

### Check Created Branches

```bash
# In your app repo
git fetch origin
git branch -r | grep auto-fix
```

### Review Pull Requests

```bash
# List auto-fix PRs
gh pr list --label "auto-fix"
```

## 🔧 Troubleshooting

### Issue: Healing pipeline not triggered

**Check:**
- GH_PAT has correct permissions
- Repository dispatch URL is correct
- `triggered_by` input is not blocking

**Solution:**
```bash
# Test the dispatch manually
curl -v -X POST \
  -H "Authorization: token YOUR_GH_PAT" \
  https://api.github.com/repos/your-org/terraform-self-healing-pipeline/dispatches \
  -d '{"event_type":"heal-deployment","client_payload":{}}'
```

### Issue: Cannot download artifacts

**Check:**
- Artifact name matches exactly
- Artifact hasn't expired (7 days default)
- GH_PAT has `repo` scope

**Solution:**
```bash
# List artifacts for a run
curl -H "Authorization: token YOUR_GH_PAT" \
  https://api.github.com/repos/owner/repo/actions/runs/RUN_ID/artifacts
```

### Issue: Fixes not being applied

**Check:**
- AI confidence is above threshold
- Files are not protected
- Branch creation succeeded

**Solution:**
- Lower `min_confidence` temporarily
- Check healing pipeline logs
- Verify file paths are correct

### Issue: Infinite loop

**Check:**
- `triggered_by` input is set correctly
- Max attempts is reasonable
- Workflow dispatch includes `triggered_by: 'self-healing-agent'`

**Solution:**
```yaml
# In healing pipeline, when triggering app workflow:
--inputs '{"triggered_by":"self-healing-agent"}'
```

## 🎓 Best Practices

### 1. Start Conservative
- Begin with `min_confidence: 0.8`
- Set `max_attempts: 3`
- Monitor first 10 healing attempts manually

### 2. Environment Strategy
- **Dev**: Auto-fix enabled, lower confidence
- **Test**: Auto-fix enabled, moderate confidence
- **Prod**: Auto-fix disabled, manual only

### 3. Review Process
- Always review auto-fix PRs before merging
- Add team members as reviewers
- Use branch protection rules

### 4. Monitoring
- Set up notifications for healing failures
- Track success rate metrics
- Review AI confidence scores

### 5. Error Patterns
- Add common errors to classifier
- Update AI prompts based on learnings
- Document recurring issues

## 📚 Additional Resources

- [Architecture Documentation](ARCHITECTURE.md)
- [API Reference](API.md)
- [Self-Healing Pipeline README](../README.md)

## 🆘 Support

- **Issues**: Open an issue in the healing pipeline repo
- **Questions**: Check existing issues or discussions
- **Improvements**: Submit a PR with enhancements
