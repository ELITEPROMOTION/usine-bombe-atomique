"""Agent #03 Terraform - genere un squelette IaC pour le livrable.

Production deterministe (aucun CLI terraform requis) :
- terraform/main.tf     : ECS Fargate service + ALB
- terraform/variables.tf : region, project_name, image_tag
- terraform/outputs.tf  : url_alb, cluster_arn
- terraform/versions.tf : providers pinning (aws ~> 5.60, random ~> 3.5)

Sanity check par regex : blocs resource/variable/output bien fermes,
noms uniques, references `var.X` toutes definies.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace

logger = logging.getLogger(__name__)


class TerraformAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-03-terraform", name="Terraform", version="1.0.0")
        self.category = "infrastructure"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        spec: str = inputs.get("spec", "")
        project = _project_name(spec)

        files = _tf_template(project)
        for rel_path, content in files.items():
            workspace.write(rel_path, content)

        issues = _sanity(files)
        score = max(0.0, 1.0 - 0.1 * len(issues))
        return {
            "score": round(score, 3),
            "passed": not issues,
            "files_written": sorted(files.keys()),
            "issues": issues,
            "project_name": project,
        }


def _project_name(spec: str) -> str:
    m = re.search(r"([a-zA-Z][a-zA-Z0-9_-]{2,})", spec or "projet")
    return (m.group(1).lower() if m else "projet")[:32]


def _tf_template(project: str) -> dict[str, str]:
    return {
        "terraform/versions.tf": f"""terraform {{
  required_version = ">= 1.6.0"
  required_providers {{
    aws    = {{ source = "hashicorp/aws",    version = "~> 5.60" }}
    random = {{ source = "hashicorp/random", version = "~> 3.5"  }}
  }}
}}

provider "aws" {{
  region = var.region
  default_tags {{
    tags = {{
      Project = "{project}"
      Managed = "terraform"
      Owner   = "Groupe Dendani"
    }}
  }}
}}
""",
        "terraform/variables.tf": f"""variable "region" {{
  description = "Region AWS"
  type        = string
  default     = "eu-west-3"
}}

variable "project_name" {{
  description = "Nom du projet (tag + prefix ressources)"
  type        = string
  default     = "{project}"
}}

variable "image_tag" {{
  description = "Tag image container a deployer"
  type        = string
  default     = "latest"
}}

variable "container_cpu" {{
  type    = number
  default = 512
}}

variable "container_memory" {{
  type    = number
  default = 1024
}}
""",
        "terraform/main.tf": """resource "random_id" "suffix" {
  byte_length = 3
}

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster-${random_id.suffix.hex}"
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${var.project_name}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.container_cpu
  memory                   = var.container_memory

  container_definitions = jsonencode([{
    name      = "app"
    image     = "${var.project_name}:${var.image_tag}"
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
}
""",
        "terraform/outputs.tf": """output "cluster_arn" {
  description = "ARN du cluster ECS"
  value       = aws_ecs_cluster.main.arn
}

output "log_group" {
  description = "Log group CloudWatch applicatif"
  value       = aws_cloudwatch_log_group.app.name
}
""",
    }


RES_RE = re.compile(r'^\s*(resource|variable|output)\s+"([^"]+)"(?:\s+"([^"]+)")?\s*{', re.M)
VAR_REF_RE = re.compile(r'var\.([a-zA-Z_][a-zA-Z0-9_]*)')
VAR_DEF_RE = re.compile(r'variable\s+"([a-zA-Z_][a-zA-Z0-9_]*)"')


def _sanity(files: dict[str, str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    all_text = "\n".join(files.values())

    # Blocs equilibres par fichier
    for path, content in files.items():
        opens = content.count("{")
        closes = content.count("}")
        if opens != closes:
            issues.append({
                "path": path,
                "message": f"Accolades desequilibrees ({opens} {{ vs {closes} }})",
            })

    # Variables referencees toutes definies
    defined = set(VAR_DEF_RE.findall(all_text))
    referenced = set(VAR_REF_RE.findall(all_text))
    missing = referenced - defined
    for name in sorted(missing):
        issues.append({"message": f"variable non definie : var.{name}"})

    return issues
