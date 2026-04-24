"""Imports et logger communs aux 7 tiers de tasks automation V5.5."""
from __future__ import annotations

import logging

from app.workers._runtime import workflow_task

logger = logging.getLogger("uba.automation.tasks")

__all__ = ["workflow_task", "logger"]
