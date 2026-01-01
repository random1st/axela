# ECS Cluster and Service

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = 14

  tags = {
    Name = "${var.app_name}-logs"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # Enable if you need detailed monitoring (costs extra)
  }

  tags = {
    Name = "${var.app_name}-cluster"
  }
}

# ECS Cluster Capacity Providers (for Fargate Spot)
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 0
    weight            = 100
    capacity_provider = "FARGATE_SPOT"
  }
}

# Task Definition
resource "aws_ecs_task_definition" "main" {
  family                   = var.app_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = var.app_name
      image     = "${var.ecr_repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "AXELA_API_HOST", value = "0.0.0.0" },
        { name = "AXELA_API_PORT", value = tostring(var.container_port) },
        { name = "AXELA_DATA_DIR", value = "/data" },
        { name = "AXELA_BASIC_AUTH_ENABLED", value = "true" },
        { name = "AXELA_BASIC_AUTH_USERNAME", value = "admin" },
        { name = "AXELA_BEDROCK_ENABLED", value = "true" },
        { name = "AXELA_BEDROCK_REGION", value = var.aws_region },
        { name = "AXELA_LOG_JSON", value = "true" },
      ]

      secrets = [
        {
          name      = "AXELA_TELEGRAM_BOT_TOKEN"
          valueFrom = aws_ssm_parameter.telegram_bot_token.arn
        },
        {
          name      = "AXELA_ENCRYPTION_KEY"
          valueFrom = aws_ssm_parameter.encryption_key.arn
        },
        {
          name      = "AXELA_BASIC_AUTH_PASSWORD"
          valueFrom = aws_ssm_parameter.basic_auth_password.arn
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "data"
          containerPath = "/data"
          readOnly      = false
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.main.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  volume {
    name = "data"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.main.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.main.id
        iam             = "ENABLED"
      }
    }
  }

  tags = {
    Name = "${var.app_name}-task"
  }
}

# ECS Service
resource "aws_ecs_service" "main" {
  name            = "${var.app_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = var.desired_count

  # Use Fargate Spot by default
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 100
    base              = 0
  }

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true # Required for public subnets without NAT
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.main.arn
    container_name   = var.app_name
    container_port   = var.container_port
  }

  # Allow external changes without Terraform plan difference
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [
    aws_lb_listener.http,
    aws_efs_mount_target.main
  ]

  tags = {
    Name = "${var.app_name}-service"
  }
}

# SSM Parameters for secrets
resource "aws_ssm_parameter" "telegram_bot_token" {
  name        = "/${var.app_name}/telegram-bot-token"
  description = "Telegram bot token"
  type        = "SecureString"
  value       = var.telegram_bot_token

  tags = {
    Name = "${var.app_name}-telegram-token"
  }
}

resource "aws_ssm_parameter" "encryption_key" {
  name        = "/${var.app_name}/encryption-key"
  description = "Fernet encryption key"
  type        = "SecureString"
  value       = var.encryption_key

  tags = {
    Name = "${var.app_name}-encryption-key"
  }
}

resource "aws_ssm_parameter" "basic_auth_password" {
  name        = "/${var.app_name}/basic-auth-password"
  description = "Basic auth password"
  type        = "SecureString"
  value       = var.basic_auth_password != "" ? var.basic_auth_password : "changeme"

  tags = {
    Name = "${var.app_name}-basic-auth-password"
  }
}
