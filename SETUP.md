# Setup Guide: Terraform Self-Healing Pipeline

## 🎯 Quick Setup (10 minutes)

This guide will help you set up the self-healing pipeline for your Terraform/Terragrunt repositories.

## 📦 Repository Structure

You now have **two repositories**:

1. **`terraform-self-healing-pipeline`** - The centralized healing pipeline (this repo)
2. **`elz-devops-tools`** - Your application repo with Terragrunt configs

## 🚀 Setup Steps

### Step 1: Configure Self-Healing Pipeline Repo

#### 1.1 Add Secrets

In the **terraform-self-healing-pipeline** repository:


Settings → Secrets and variables → Actions → New repository secret

ANTHROPIC_API_KEY    # Get from console.anthropic.com
GH_PAT               # GitHub Personal Access Token (see below)


#### 1.2 Create GitHub Personal Access Token

Create a PAT with these scopes:
- `repo` (full control of private repositories)
- `workflow` (update GitHub Action workflows)

Create at: https://github.com/settings/tokens/new

**Important**: This PAT will be used to:
- Download artifacts from app repos
- Clone app repos
- Create branches in app repos
- Trigger workflows in app repos
- Create pull requests

### Step 2: Configure Application Repo (elz-devops-tools)

#### 2.1 Add Secrets

In the **elz-devops-tools** repository:


Settings → Secrets and variables → Actions → New repository secret

ANTHROPIC_API_KEY           # Same as above
GH_PAT                      # Same PAT as above
DEV_AWS_OIDC_ROLE_ARN      # Your AWS role for dev
TEST_AWS_OIDC_ROLE_ARN     # Your AWS role for test (optional)
PROD_AWS_OIDC_ROLE_ARN     # Your AWS role for prod (optional)


#### 2.2 Enable Workflow Permissions


Settings → Actions → General
→ Workflow permissions: "Read and write permissions"
→ Check "Allow GitHub Actions to create and approve pull requests"
→ Save


### Step 3: Update Repository URLs

#### 3.1 In elz-devops-tools workflow

Edit `.github/workflows/terragrunt-deployment.yaml`:

yaml
# Line ~201 and ~325
https://api.github.com/repos/YOUR-ORG/terraform-self-healing-pipeline/dispatches


Replace `YOUR-ORG` with your GitHub organization or username.

#### 3.2 In healing pipeline workflow

No changes needed - it uses dynamic values from the dispatch event.

### Step 4: Test the Integration

#### 4.1 Introduce a Test Error

bash
cd /home/aumni/Documents/PoleStar/GitHub/elz-devops-tools

# Create a test branch
git checkout -b test-self-healing

# Introduce a known error (provider version mismatch)
cat >> provision/hoppscotch/versions.tf <<EOF

# Test error - wrong version
# This will cause a provider version mismatch
EOF

git add provision/hoppscotch/versions.tf
git commit -m "Test: Trigger self-healing pipeline"
git push origin test-self-healing


#### 4.2 Watch the Magic

1. **App Repo Workflow Fails**
   - Go to elz-devops-tools → Actions
   - See deployment fail
   - Error logs uploaded as artifact

2. **Healing Pipeline Triggered**
   - Go to terraform-self-healing-pipeline → Actions
   - See "Self-Healing Agent" workflow start
   - Watch it analyze, fix, and redeploy

3. **Fix Branch Created**
   - New branch created: `auto-fix/dev-TIMESTAMP-attempt-1`
   - Fixes committed to this branch
   - Deployment retriggered

4. **PR Created**
   - If successful, PR created for review
   - Review and merge the fix

## 🔄 How It Works

### Normal Flow (Success)


Push to develop
  ↓
Terragrunt Deployment
  ↓
Success ✅
  ↓
Done


### Self-Healing Flow (Failure)


Push to develop
  ↓
Terragrunt Deployment
  ↓
Failure ❌
  ↓
Upload error logs
  ↓
Trigger healing pipeline (repository_dispatch)
  ↓
┌─────────────────────────────────────────┐
│ Healing Pipeline Repo                   │
│                                          │
│ 1. Download error logs                  │
│ 2. Clone app repo                       │
│ 3. Analyze with AI                      │
│ 4. Generate fix                         │
│ 5. Create branch: auto-fix/...          │
│ 6. Commit fixes                         │
│ 7. Push to app repo                     │
│ 8. Trigger app workflow                 │
└─────────────────────────────────────────┘
  ↓
Redeployment on fix branch
  ↓
Success ✅
  ↓
Create PR for review


## 📋 Configuration

### Adjust Confidence Thresholds

In `elz-devops-tools/.github/workflows/terragrunt-deployment.yaml`:

yaml
# For dev environment (line ~211)
"min_confidence": 0.7    # 70% confidence required

# For test environment (line ~336)
"min_confidence": 0.75   # 75% confidence required

# For prod - disable auto-fix entirely


### Adjust Max Attempts

yaml
"max_attempts": 10    # Try up to 10 times


### Change Workflow to Trigger

yaml
"workflow_to_trigger": "terragrunt-deployment.yaml"


## 🛡️ Safety Features

### Branch Isolation
- All fixes in separate branches
- Pattern: `auto-fix/{env}-{timestamp}-attempt-{N}`
- Never modifies main/develop directly

### Loop Prevention
- `triggered_by` input prevents infinite loops
- Max attempts limited to 10
- Each attempt creates a new branch

### Confidence Scoring
- AI provides confidence score (0-1)
- Only applies fixes above threshold
- Lower confidence = manual review required

### File Protection
- Never modifies `.terraform/` directories
- Never modifies state files
- Never modifies secret files
- Validates file paths before changes

## 🐛 Troubleshooting

### Common Issues

1. **"Authentication failed"**
   - Check GH_PAT has correct permissions
   - Ensure PAT isn't expired

2. **"Artifact not found"**
   - Check artifact name matches exactly
   - Ensure error log was uploaded before dispatch

3. **"AI confidence too low"**
   - Review error logs manually
   - Lower confidence threshold temporarily
   - Add context to Terragrunt comments

4. **"Max attempts reached"**
   - Review all attempted fixes
   - May need manual intervention
   - Check for complex dependency issues

### Debug Mode

Enable debug logging by adding:

yaml
env:
  ACTIONS_STEP_DEBUG: true
  ACTIONS_RUNNER_DEBUG: true


## 📊 Monitoring

### Success Metrics

- **Fix Success Rate**: % of deployments automatically fixed
- **Time to Resolution**: Average time from failure to fix
- **Confidence Distribution**: AI confidence scores over time
- **Error Categories**: Most common error types

### Logging

All actions are logged:
- Error analysis results
- Generated fixes with confidence
- Branch creation and commits
- Deployment monitoring
- PR creation

## 🎯 Best Practices

### For Developers

1. **Write Clear Commit Messages**
   - Helps AI understand context
   - Include purpose of changes

2. **Add Comments to Complex Logic**
   - AI uses comments for context
   - Explain non-obvious configurations

3. **Test in Feature Branches**
   - Use feature branches for complex changes
   - Let self-healing fix issues before merging

### For Operators

1. **Monitor Success Rates**
   - Low success rate indicates need for tuning
   - Add patterns to error classifier

2. **Review Auto-Generated PRs**
   - Understand common fix patterns
   - Merge successful fixes quickly

3. **Adjust Thresholds by Environment**
   - Higher confidence for production
   - More attempts for development

## 🔒 Security

### Secrets Management

- Use repository secrets, not hardcoded values
- Rotate PATs regularly
- Limit PAT scope to minimum required

### Code Safety

- All fixes in isolated branches
- Manual review via PR process
- No direct commits to main branches
- State file protection built-in

## 📈 Advanced Configuration

### Custom Error Patterns

Add custom error patterns in `error-classifier.py`:

python
custom_patterns = {
    'vpc_limit': {
        'pattern': r'VpcLimitExceeded',
        'category': 'resource_limit',
        'confidence': 0.9
    }
}


### Environment-Specific Settings

yaml
# Development: More aggressive fixing
dev:
  max_attempts: 10
  min_confidence: 0.6
  auto_merge: false

# Test: Balanced approach  
test:
  max_attempts: 5
  min_confidence: 0.75
  auto_merge: false

# Production: Conservative approach
prod:
  max_attempts: 0  # Disabled
  min_confidence: 0.9
  auto_merge: false
