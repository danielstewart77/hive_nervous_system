"""Memory (vector store) endpoints for the lucent-api nervous-system service.

Wraps tools.stateful.lucent_memory public functions in FastAPI routes.
No auth and no HITL — internal Docker-network only.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


def _decode(payload: str) -> Any:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"error": "invalid_json_from_underlying_function", "raw": payload}


# ---- Request schemas ----


class StoreBody(BaseModel):
    content: str
    data_class: str
    mind_id: str = "ada"
    tier: str = "contextual"
    tags: str = ""
    source: str = "user"
    as_of: str | None = None
    expires_at: str | None = None
    recurring: bool | None = None
    codebase_ref: str | None = None


class UpdateBody(BaseModel):
    content: str = ""
    data_class: str = ""
    tags: str = ""


# ---- Read endpoints ----


@router.get("/list")
def memory_list(
    mind_id: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    tier: str | None = Query(None),
) -> Any:
    """List memories sequentially by creation time.

    Optional ``tier`` and ``mind_id`` filters. ``mind_id`` is opt-in —
    omit for cross-mind reads (default REQ-006 behavior), pass exactly
    when you want a provenance filter (e.g. the bootstrap-loader's
    per-mind + ``shared`` standing-rules union).
    """
    from lucent_api.lucent_memory import memory_list as _memory_list

    return _decode(
        _memory_list(offset=offset, limit=limit, mind_id=mind_id, tier=tier)
    )


@router.get("/recent-decayed")
def memory_recent_decayed(
    limit: int = Query(20, ge=1, le=100),
) -> Any:
    """Top-N contextual entries scored by recency decay (REQ-024)."""
    from lucent_api.lucent_memory import query_decayed

    return _decode(query_decayed(limit=limit))


@router.get("/retrieve")
def memory_retrieve(
    query: str = Query(...),
    mind_id: str = Query("ada"),
    k: int = Query(10, ge=1, le=50),
    tag_filter: str | None = Query(None),
    data_class: str | None = Query(None),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
) -> Any:
    """Semantic search — return top-k memories most relevant to the query.

    Optional filters:
      data_class — keep only entries matching the given class.
      min_score  — drop entries below this cosine similarity (0.0–1.0).
    """
    from lucent_api.lucent_memory import memory_retrieve as _memory_retrieve

    return _decode(
        _memory_retrieve(
            query=query,
            k=k,
            mind_id=mind_id,
            tag_filter=tag_filter,
            data_class=data_class,
            min_score=min_score,
        )
    )


# ---- Write endpoints ----


@router.post("/store")
def memory_store(body: StoreBody) -> Any:
    """Store a memory with semantic embedding."""
    from lucent_api.lucent_memory import memory_store as _memory_store

    return _decode(
        _memory_store(
            content=body.content,
            data_class=body.data_class,
            tier=body.tier,
            tags=body.tags,
            source=body.source,
            mind_id=body.mind_id,
            as_of=body.as_of,
            expires_at=body.expires_at,
            recurring=body.recurring,
            codebase_ref=body.codebase_ref,
        )
    )


@router.put("/{memory_id}")
def memory_update(memory_id: str, body: UpdateBody) -> Any:
    """Update an existing memory's content, data_class, or tags."""
    from lucent_api.lucent_memory import memory_update as _memory_update

    return _decode(
        _memory_update(
            memory_id=memory_id,
            content=body.content,
            data_class=body.data_class,
            tags=body.tags,
        )
    )


@router.delete("/{memory_id}")
def memory_delete(memory_id: str) -> Any:
    """Delete a memory by ID."""
    from lucent_api.lucent_memory import memory_delete as _memory_delete

    return _decode(_memory_delete(memory_id=memory_id))
