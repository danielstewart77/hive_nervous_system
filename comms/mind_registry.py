"""
Hive Mind -- Mind registry.

In-memory cache of registered minds, hydrated from broker.minds at
startup and kept in sync by /broker/minds writes. There is no
filesystem scan — minds are sourced exclusively from the broker DB.
See backlog/mind-registration-service.md for the Layer 2 provisioning
service that creates the broker rows.
"""

import logging
from dataclasses import dataclass, field

log = logging.getLogger("hive-mind.mind_registry")


@dataclass
class MindInfo:
    """Routing-layer record for one mind."""

    mind_id: str        # UUID — registry key, stamped on lucent writes
    name: str           # display label (e.g. "skippy")
    model: str          # e.g. "claude-sonnet-4-6", "gpt-oss:20b-32k"
    harness: str        # e.g. "claude_cli_claude", "codex_cli_codex"
    gateway_url: str    # e.g. "http://host.docker.internal:8421"
    prompt_files: list[str] = field(default_factory=list)


class MindRegistry:
    """In-memory cache of minds, keyed by mind_id (UUID)."""

    def __init__(self) -> None:
        self._minds: dict[str, MindInfo] = {}

    def upsert(self, info: MindInfo) -> None:
        """Add or replace a mind by UUID."""
        self._minds[info.mind_id] = info
        log.info(
            "Registered mind: %s [%s] @ %s (harness=%s, model=%s)",
            info.name, info.mind_id, info.gateway_url, info.harness, info.model,
        )

    def remove(self, mind_id: str) -> None:
        """Drop a mind from the cache."""
        self._minds.pop(mind_id, None)

    def get(self, mind_id: str) -> MindInfo | None:
        """Look up a mind by UUID (mind_id)."""
        return self._minds.get(mind_id)

    def list_all(self) -> list[MindInfo]:
        """Return all registered minds."""
        return list(self._minds.values())

    def load_from_rows(self, rows: list[dict]) -> None:
        """Bulk-load from broker.minds rows (called at lifespan startup).

        Rows come from broker.get_registered_minds, which surfaces mind_id
        as ``id`` per the broker-minds API contract.
        """
        for row in rows:
            self.upsert(MindInfo(
                mind_id=row["id"],
                name=row["name"],
                model=row["model"],
                harness=row["harness"],
                gateway_url=row["gateway_url"],
            ))
