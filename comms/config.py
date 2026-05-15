"""Minimal comms config — env-driven.

A1 stub. The full config schema (providers, model lists, etc.) is wired
in A3 when the model registry is reconciled. For now this satisfies the
``from config import PROJECT_DIR, config`` import in ``comms/server.py``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("COMMS_PROJECT_DIR", "/app")).resolve()


@dataclass
class _Config:
    server_port: int = int(os.environ.get("COMMS_PORT", "8424"))
    providers: dict = field(default_factory=dict)
    models: list = field(default_factory=list)


config = _Config()
