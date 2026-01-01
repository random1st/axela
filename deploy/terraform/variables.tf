# Variables for Axela ECS Fargate Spot deployment

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "axela"
}

# Networking - use existing VPC
variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs (for ALB, ECS, EFS)"
  type        = list(string)
}

variable "ecr_repository_url" {
  description = "ECR repository URL (created externally)"
  type        = string
}

# ECS
variable "container_port" {
  description = "Container port"
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Fargate CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "memory" {
  description = "Fargate memory in MB"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Desired number of tasks"
  type        = number
  default     = 1
}

# Secrets (passed via environment or tfvars)
variable "telegram_bot_token" {
  description = "Telegram bot token"
  type        = string
  sensitive   = true
}

variable "encryption_key" {
  description = "Fernet encryption key for credentials"
  type        = string
  sensitive   = true
}

variable "basic_auth_password" {
  description = "Basic auth password for web UI"
  type        = string
  sensitive   = true
  default     = ""
}
