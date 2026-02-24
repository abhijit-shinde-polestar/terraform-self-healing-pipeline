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

```
Settings → Secrets and variables → Actions → New repository secret

ANTHROPIC_API_KEY    # Get from console.anthropic.com
GH_PAT               # GitHub Personal Access Token (see below)
```

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

```
Settings → Secrets and variables → Actions → New repository secret

ANTHROPIC_API_KEY           # Same as above
GH_PAT                      # Same PAT as above
DEV_AWS_OIDC_ROLE_ARN      # Your AWS role for dev
TEST_AWS_OIDC_ROLE_ARN     # Your AWS role for test (optional)
PROD_AWS_OIDC_ROLE_ARN     # Your AWS role for prod (optional)
```

#### 2.2 Enable Workflow Permissions

```
Settings → Actions → General
→ Workflow permissions: "Read and write permissions"
→ Check "Allow GitHub Actions to create and approve pull requests"
→ Save
```

### Step 3: Update Repository URLs

#### 3.1 In elz-devops-tools workflow

Edit `.github/workflows/terragrunt-deployment.yaml`:

```yaml
# Line ~201 and ~325
https://api.github.com/repos/YOUR-ORG/terraform-self-healing-pipeline/dispatches
```

Replace `YOUR-ORG` with your GitHub organization or username.

#### 3.2 In healing pipeline workflow

No changes needed - it uses dynamic values from the dispatch event.

### Step 4: Test the Integration

#### 4.1 Introduce a Test Error

```bash
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
```

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

```
Push to develop
  ↓
Terragrunt Deployment
  ↓
Success ✅
  ↓
Done
```

### Self-Healing Flow (Failure)

```
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
```

## 📋 Configuration

### Adjust Confidence Thresholds

In `elz-devops-tools/.github/workflows/terragrunt-deployment.yaml`:

```yaml
# For dev environment (line ~211)
"min_confidence": 0.7    # 70% confidence required

# For test environment (line ~336)
"min_confidence": 0.75   # 75% confidence required

# For prod - disable auto-fix entirely
```

### Adjust Max Attempts

```yaml
"max_attempts": 5    # Try up to 5 times
```

### Change Workflow to Trigger

```yaml
"workflow_to_trigger": "terragrunt-deployment.yaml"
```

## 🛡️ Safety Features

### Branch Isolation
- All fixes in separate branches
- Pattern: `auto-fix/{env}-{timestamp}-attempt-{N}`
- Never modifies main/develop directly

### Loop Prevention
- `triggered_by` input prevents infinite loops
- Max attempts limit
- Only triggers if not already triggered by healing agent

### File Protection
- Never modifies `.tfstate` files
- Never modifies lock files
- Blocks dangerous operations

### Confidence Thresholds
- AI must be confident (70%+ default)
- Low confidence fixes rejected
- Manual intervention for uncertain cases

## 🧪 Verification Checklist

- [ ] Secrets added to both repos
- [ ] GH_PAT has correct permissions
- [ ] Workflow permissions enabled
- [ ] Repository URLs updated
- [ ] Test error introduced
- [ ] Deployment fails as expected
- [ ] Healing pipeline triggered
- [ ] Fix branch created
- [ ] Deployment succeeds on fix branch
- [ ] PR created for review

## 📊 Monitoring

### View Healing Attempts

```bash
# In healing pipeline repo
cd /home/aumni/Documents/PoleStar/GitHub/terraform-self-healing-pipeline

# Check workflow runs
gh run list --workflow=self-healing-agent.yaml
```

### Check Created Branches

```bash
# In app repo
cd /home/aumni/Documents/PoleStar/GitHub/elz-devops-tools

# List auto-fix branches
git fetch origin
git branch -r | grep auto-fix
```

### Review PRs

```bash
# List auto-fix PRs
gh pr list --search "author:app/github-actions"
```

## 🔧 Troubleshooting

### Healing Pipeline Not Triggered

**Symptoms**: Deployment fails but healing pipeline doesn't start

**Check**:
```bash
# Verify GH_PAT is set
gh secret list --repo your-org/elz-devops-tools | grep GH_PAT

# Test repository dispatch manually
curl -X POST \
  -H "Authorization: token YOUR_GH_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/your-org/terraform-self-healing-pipeline/dispatches \
  -d '{"event_type":"heal-deployment","client_payload":{"source_repo":"your-org/elz-devops-tools"}}'
```

### Cannot Download Artifacts

**Symptoms**: Healing pipeline fails at artifact download step

**Check**:
- Artifact name matches exactly
- Artifact hasn't expired (7 days)
- GH_PAT has `repo` scope

**Fix**:
```bash
# List artifacts for a run
curl -H "Authorization: token YOUR_GH_PAT" \
  https://api.github.com/repos/your-org/elz-devops-tools/actions/runs/RUN_ID/artifacts
```

### Fixes Not Applied

**Symptoms**: AI generates fix but files not modified

**Check**:
- AI confidence above threshold
- Files not in protected list
- Branch creation succeeded

**Fix**:
- Lower `min_confidence` temporarily
- Check healing pipeline logs
- Verify file paths are correct

### Infinite Loop

**Symptoms**: Deployment keeps retriggering

**Check**:
- `triggered_by` input is set
- Workflow includes the check

**Fix**:
```yaml
# Ensure this condition is present
if: |
  failure() && 
  steps.deploy.outcome == 'failure' &&
  github.event.inputs.triggered_by != 'self-healing-agent'
```

## 🎓 Best Practices

### 1. Start Conservative
- Set `min_confidence: 0.8` initially
- Set `max_attempts: 3`
- Monitor first 10 healing attempts

### 2. Environment Strategy
- **Dev**: Auto-fix enabled, confidence 0.6-0.7
- **Test**: Auto-fix enabled, confidence 0.7-0.8
- **Prod**: Auto-fix disabled, manual only

### 3. Review Process
- Always review auto-fix PRs
- Add required reviewers
- Use branch protection

### 4. Gradual Rollout
1. Test in dev environment
2. Monitor for 1 week
3. Enable in test
4. Keep prod manual

## 📚 Next Steps

1. **Test the setup** - Introduce a test error
2. **Monitor results** - Watch first few healing attempts
3. **Tune settings** - Adjust confidence thresholds
4. **Add patterns** - Customize error classifier
5. **Scale up** - Apply to other repos

## 🆘 Support

- **Documentation**: See [docs/INTEGRATION.md](docs/INTEGRATION.md)
- **Issues**: Open issue in healing pipeline repo
- **Questions**: Check existing issues

---

**Ready?** Push a change to elz-devops-tools and watch the self-healing in action! 🚀
