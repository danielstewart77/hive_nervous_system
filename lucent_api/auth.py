"""Bearer-token auth middleware (F9).

Validates ``Authorization: Bearer <token>`` against ``LUCENT_BEARER_TOKEN``
env var. Health endpoint and root stay open; every other route uses this
as a dependency.

Empty/unset env var = bypass with a startup warning. This is a deployment
safety: a fresh container won't accidentally lock itself out before the
operator gets a chance to set the token. Once ``LUCENT_BEARER_TOKEN`` is
set, validation is enforced and unauthenticated requests get 401.
"""
from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException

log = logging.getLogger(__name__)


def require_bearer(authorization: str = Header(default="")) -> None:
    expected = os.environ.get("LUCENT_BEARER_TOKEN", "")
    if not expected:
        # Bypass mode. Logged once at module load time below.
        return
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    if authorization[7:] != expected:
        raise HTTPException(401, "Invalid token")


# Startup warning when bypass is active.
if not os.environ.get("LUCENT_BEARER_TOKEN"):
    log.warning(
        "LUCENT_BEARER_TOKEN is unset — auth bypass active. "
        "Set the env var to enforce bearer-token gating."
    )
