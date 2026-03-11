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


Settings → Secrets and variables → Actions → New repository secret

ANTHROPIC_API_KEY    # Claude API key from console.anthropic.com
GH_PAT               # GitHub Personal Access Token (see below)


### Step 2: Create GitHub Personal Access Token

The `GH_PAT` needs these permissions:
- `repo` (full control)
- `workflow` (update workflows)

Create it at: https://github.com/settings/tokens/new

### Step 3: Update Your Deployment Workflow

Add the self-healing trigger to your existing deployment workflow:

yaml
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
                "max_attempts": 10,
                "min_confidence": 0.7,
                "run_id": "${{ github.run_id }}"
              }
            }'


### Step 4: Add Workflow Dispatch Input

To prevent infinite loops, add this input to your workflow:

yaml
on:
  workflow_dispatch:
    inputs:
      triggered_by:
        description: 'Triggered by (internal use)'
        required: false
        type: string
        default: 'manual'


## 🔄 How It Works

### Flow Diagram


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
│  13. Redeployment triggered on fix branch                   │
│  14. If success → Create PR                                 │
│      If failure → Repeat from step 5 (max 10 attempts)     │
└─────────────────────────────────────────────────────────────┘
