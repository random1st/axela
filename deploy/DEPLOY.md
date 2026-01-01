# Axela AWS Deployment Guide

This guide covers deploying Axela to AWS using ECS Fargate Spot with EFS for SQLite persistence.

## Architecture

Uses your **existing VPC** with public/private subnets.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Existing VPC                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Public Subnets                         │   │
│  │                      ┌───────────────┐                   │   │
│  │                      │      ALB      │◄───HTTP───────────│   │
│  │                      └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Private Subnets                         │   │
│  │  ┌───────────────────────────────────────────────────┐  │   │
│  │  │              ECS Fargate Spot                      │  │   │
│  │  │  ┌─────────────────────────────────────────────┐  │  │   │
│  │  │  │              Axela Container                 │  │  │   │
│  │  │  │  - FastAPI + Jinja2 + HTMX                  │  │  │   │
│  │  │  │  - AWS Bedrock (AI summarization)           │  │  │   │
│  │  │  │  - Telegram Bot                             │  │  │   │
│  │  │  └─────────────────────────────────────────────┘  │  │   │
│  │  └───────────────────────────────────────────────────┘  │   │
│  │                              │                           │   │
│  │                      ┌───────▼───────┐                   │   │
│  │                      │      EFS      │                   │   │
│  │                      │  (SQLite DB)  │                   │   │
│  │                      └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Cost Estimate (us-east-1)

| Resource | Monthly Cost |
|----------|--------------|
| ECS Fargate Spot (0.25 vCPU, 512MB) | ~$3-5 |
| ALB | ~$16 + LCU |
| EFS | ~$0.30/GB |
| CloudWatch Logs | ~$0.50 |
| **Total** | **~$20-25/month** |

> Uses existing VPC/NAT, so no additional VPC costs.

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.0
3. **Docker** for building images
4. **Telegram Bot Token** from @BotFather
5. **Fernet Encryption Key** for credentials storage

### Generate Fernet Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Initial Setup

### 1. Set Secrets

```bash
export AWS_PROFILE=random1st
export TF_VAR_telegram_bot_token="YOUR_BOT_TOKEN"
export TF_VAR_encryption_key="YOUR_FERNET_KEY"
export TF_VAR_basic_auth_password="YOUR_PASSWORD"
```

### 2. Deploy Infrastructure

```bash
export AWS_PROFILE=random1st

cd deploy/terraform

# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply (creates all resources)
terraform apply
```

### 3. Build and Push Docker Image

After `terraform apply` completes:

```bash
# Get ECR login command from Terraform output
$(terraform output -raw docker_login_command)

# Build and push
cd ../..  # Back to project root
docker build -t axela .
docker tag axela:latest $(terraform output -raw ecr_repository_url):latest
docker push $(terraform output -raw ecr_repository_url):latest

# Force ECS to deploy new image
$(terraform output -raw ecs_update_command)
```

### 4. Access the Application

После деплоя приложение доступно по адресу: **https://axela.app**

Login с Basic Auth credentials которые вы указали в tfvars.

## GitHub Actions Deployment

### Setup OIDC for GitHub Actions

1. Create IAM OIDC provider for GitHub:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

2. Create IAM role for GitHub Actions (replace `YOUR_GITHUB_ORG/YOUR_REPO`):

```bash
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_ORG/YOUR_REPO:*"
        }
      }
    }
  ]
}
EOF

aws iam create-role \
  --role-name axela-github-actions \
  --assume-role-policy-document file://trust-policy.json
```

3. Attach required policies:

```bash
# ECR access
aws iam attach-role-policy \
  --role-name axela-github-actions \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

# ECS access
aws iam attach-role-policy \
  --role-name axela-github-actions \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess
```

4. Add GitHub secret `AWS_ROLE_ARN` with the role ARN.

## Operations

### View Logs

```bash
# Recent logs
aws logs tail /ecs/axela --follow

# Or via AWS Console: CloudWatch > Log Groups > /ecs/axela
```

### Force Redeploy

```bash
aws ecs update-service \
  --cluster axela-cluster \
  --service axela-service \
  --force-new-deployment
```

### Scale Service

```bash
aws ecs update-service \
  --cluster axela-cluster \
  --service axela-service \
  --desired-count 2
```

### SSH to Container (for debugging)

```bash
# Enable ECS Exec first (in task definition)
aws ecs execute-command \
  --cluster axela-cluster \
  --task TASK_ID \
  --container axela \
  --interactive \
  --command "/bin/sh"
```

## Cleanup

```bash
cd deploy/terraform

# Destroy all resources
terraform destroy
```

## Troubleshooting

### Container fails to start

1. Check CloudWatch logs
2. Verify all secrets are set in SSM Parameter Store
3. Check ECS task stopped reason in AWS Console

### Database errors

1. Check EFS mount target connectivity
2. Verify security group allows NFS (port 2049) from ECS tasks
3. Check EFS access point permissions

### Fargate Spot interruptions

Fargate Spot can be interrupted with 2-minute warning. The service will automatically restart tasks. For critical workloads, use regular Fargate by changing capacity provider strategy.

### Health check failures

1. Verify `/health` endpoint returns 200
2. Check container has enough time to start (increase `startPeriod`)
3. Check ALB target group health check settings
