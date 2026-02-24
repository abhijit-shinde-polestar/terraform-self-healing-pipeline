# Terraform Self-Healing Pipeline

A reusable, autonomous CI/CD pipeline that automatically detects, classifies, fixes, and redeploys failed Terraform/Terragrunt deployments using AI.

## 🎯 Overview

This repository provides a **centralized self-healing pipeline** that can be called from any Terraform/Terragrunt repository when deployments fail. It uses AI (Claude) to analyze errors, generate fixes, create branches, commit changes, and trigger redeployment.

## 🚀 Features

- ✅ **Cross-Repository Integration**: Can be called from any repo via workflow dispatch
- ✅ **AI-Powered Analysis**: Uses Claude to understand and fix errors
- ✅ **Automatic Branch Creation**: Creates fix branches in the source repo
- ✅ **Auto-Commit & Push**: Commits fixes and pushes to new branch
- ✅ **Workflow Retriggering**: Automatically retriggers deployment workflow
- ✅ **Safety Rails**: Multiple validation layers
- ✅ **Retry Loop**: Continues until success or max attempts

## 📁 Repository Structure

```
terraform-self-healing-pipeline/
├── .github/
│   ├── workflows/
│   │   ├── self-healing-agent.yaml      # Main healing workflow
│   │   └── test-healing.yaml            # Testing workflow
│   ├── actions/
│   │   └── analyze-and-fix/             # Reusable action
│   │       └── action.yaml
│   └── scripts/
│       ├── ai-healing-agent.py          # AI agent
│       ├── error-classifier.py          # Error classification
│       ├── github-integration.py        # Cross-repo operations
│       └── requirements.txt
├── config/
│   └── self-healing-config.yaml         # Configuration
├── docs/
│   ├── ARCHITECTURE.md                  # System architecture
│   ├── INTEGRATION.md                   # Integration guide
│   └── API.md                           # API reference
└── README.md
```

## 🔧 Quick Start

### For Application Repositories (e.g., elz-devops-tools)

Add this to your deployment workflow:

```yaml
- name: Call Self-Healing Pipeline on Failure
  if: failure()
  uses: your-org/terraform-self-healing-pipeline/.github/workflows/self-healing-agent.yaml@main
  with:
    source_repo: ${{ github.repository }}
    source_ref: ${{ github.ref }}
    error_log_path: deployment-error.log
    terragrunt_path: workloads/polestar/hoppscotch
  secrets:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    GH_PAT: ${{ secrets.GH_PAT }}
```

### Required Secrets

Add these to your **application repository**:

```
ANTHROPIC_API_KEY    # Claude API key
GH_PAT               # GitHub Personal Access Token with repo scope
```

## 📖 Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Integration Guide](docs/INTEGRATION.md) - How to integrate with your repos
- [API Reference](docs/API.md) - Workflow inputs and outputs

## 🔄 How It Works

```
App Repo Deployment Fails
    ↓
Calls Self-Healing Pipeline (this repo)
    ↓
Analyzes Error with AI
    ↓
Generates Fix
    ↓
Creates Branch in App Repo (e.g., auto-fix/deployment-123)
    ↓
Commits Fix to Branch
    ↓
Pushes to App Repo
    ↓
Triggers App Repo Deployment Workflow
    ↓
Monitors Deployment
    ↓
Repeats Until Success or Max Attempts
```

## 🛡️ Safety Features

- **Confidence Thresholds**: Requires 70%+ AI confidence
- **File Protection**: Never modifies state files or secrets
- **Branch Isolation**: All fixes in separate branches
- **Manual Review**: Creates PRs for review before merge
- **Attempt Limits**: Max 5 retry attempts
- **Audit Trail**: Complete logging of all actions

## 🎓 Examples

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for complete examples of:
- Terragrunt deployments
- Multi-environment setups
- Monorepo configurations
- Custom error patterns

## 📊 Monitoring

The pipeline provides detailed outputs:
- Fix success rate
- Error categories
- Confidence scores
- Time to resolution
- Branch names created

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new error patterns
4. Submit a pull request

## 📄 License

MIT License - See LICENSE file