"""Knowledge graph schema source of truth.

Hardcoded for now per design decision 2026-05-10. The companion human-facing
spec at `spark_to_bloom/src/backlog/knowledge-graph-tidy.md` exists for
documentation; this file is what the running system trusts. Once enforcement
is in place and migration has run, the backlog file gets deleted.

Schema shape per type:
    name → {
        kind:     "first-class" | "second-class",
        required: [field names that callers must supply],
        optional: [field names callers may supply],
        enums:    { field_name: [allowed values] },
    }

Edges:
    name → {
        source_type:     <node type>,
        target_type:     <node type>,
        required_attrs:  [edge attr names],
        optional_attrs:  [edge attr names],
        enums:           { attr_name: [allowed values] },
        symmetric:       bool,
    }

`agent_id`, `id`, `created_at`, `updated_at` are infrastructure fields handled
by the write path — they are NOT user-supplied and NOT validated here.
"""

from __future__ import annotations


SCHEMA_TYPES: dict[str, dict] = {
    # ---- First-class ----
    "Person": {
        "kind": "first-class",
        "required": ["name"],
        "optional": ["first_name", "last_name"],
        "enums": {},
    },
    "Mind": {
        "kind": "first-class",
        "required": ["name"],
        "optional": [],
        "enums": {},
    },
    "Device": {
        "kind": "first-class",
        "required": ["name", "kind"],
        "optional": ["purpose", "as_of", "config"],
        "enums": {
            "kind": ["phone", "laptop", "desktop", "server", "workstation", "tablet", "iot"],
        },
    },
    "Organization": {
        "kind": "first-class",
        "required": ["name"],
        "optional": ["full_name", "kind", "email", "phone", "website", "as_of"],
        "enums": {},
    },
    # ---- Person facets ----
    "ContactMethod": {
        "kind": "second-class",
        "required": ["kind", "value"],
        "optional": ["label", "as_of"],
        "enums": {
            "kind": ["email", "phone", "telegram", "discord", "slack", "mailing_address"],
            "label": ["work", "personal", "school", "planka"],
        },
    },
    "Place": {
        "kind": "second-class",
        "required": ["name", "kind"],
        "optional": ["as_of"],
        "enums": {
            "kind": ["home", "work", "school", "city", "country"],
        },
    },
    "Address": {
        "kind": "second-class",
        "required": ["street"],
        "optional": ["city", "state", "postal_code", "country", "label", "as_of"],
        "enums": {
            "label": ["home", "work", "mailing"],
        },
    },
    "Employment": {
        "kind": "second-class",
        "required": ["employer_name"],
        "optional": ["title", "since", "until"],
        "enums": {},
    },
    "Interest": {
        "kind": "second-class",
        "required": ["name", "kind"],
        "optional": ["notes", "as_of"],
        "enums": {
            "kind": ["hobby", "sport", "media", "topic", "food"],
        },
    },
    "HealthFact": {
        "kind": "second-class",
        "required": ["summary"],
        "optional": ["relevance", "as_of"],
        "enums": {
            "relevance": ["informational", "actionable", "dietary", "medication"],
        },
    },
    "Aspiration": {
        "kind": "second-class",
        "required": ["summary"],
        "optional": ["as_of"],
        "enums": {},
    },
    # ---- Mind facets ----
    "Skill": {
        "kind": "second-class",
        "required": ["name"],
        "optional": ["source", "last_used"],
        "enums": {
            "source": ["user-config", "plugin", "built-in"],
        },
    },
    "Tool": {
        "kind": "second-class",
        "required": ["name"],
        "optional": ["source"],
        "enums": {
            "source": ["mcp", "builtin", "http"],
        },
    },
    "Runtime": {
        "kind": "second-class",
        "required": ["harness"],
        "optional": ["provider"],
        "enums": {
            "harness": ["claude_cli", "codex_cli", "claude_sdk", "codex_sdk"],
            "provider": ["anthropic", "ollama", "openai"],
        },
    },
    "SoulValue": {
        "kind": "second-class",
        "required": ["text"],
        "optional": ["as_of"],
        "enums": {},
    },
    # ---- Device facets ----
    "OS": {
        "kind": "second-class",
        "required": ["name"],
        "optional": ["version", "as_of"],
        "enums": {},
    },
    "Software": {
        "kind": "second-class",
        "required": ["name"],
        "optional": ["purpose", "as_of"],
        "enums": {},
    },
}


SCHEMA_EDGES: dict[str, dict] = {
    "HAS_CONTACT": {
        "source_type": "Person",
        "target_type": "ContactMethod",
        "required_attrs": [],
        "optional_attrs": ["is_primary"],
        "enums": {},
        "symmetric": False,
    },
    "LIVES_IN": {
        "source_type": "Person",
        "target_type": "Place",
        "required_attrs": [],
        "optional_attrs": ["since"],
        "enums": {},
        "symmetric": False,
    },
    "HAS_ADDRESS": {
        "source_type": "Person",
        "target_type": "Address",
        "required_attrs": [],
        "optional_attrs": ["since", "until"],
        "enums": {},
        "symmetric": False,
    },
    "WORKS_IN": {
        "source_type": "Person",
        "target_type": "Place",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "WORKS_AT": {
        "source_type": "Person",
        "target_type": "Employment",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "LOCATED_AT": {
        "source_type": "Employment",
        "target_type": "Place",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "HAS_SIDE_GIG": {
        "source_type": "Person",
        "target_type": "Organization",
        "required_attrs": [],
        "optional_attrs": ["since", "until"],
        "enums": {},
        "symmetric": False,
    },
    "FOUNDED_BY": {
        "source_type": "Organization",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": ["since"],
        "enums": {},
        "symmetric": False,
    },
    "INTERESTED_IN": {
        "source_type": "Person",
        "target_type": "Interest",
        "required_attrs": [],
        "optional_attrs": ["strength", "since"],
        "enums": {},
        "symmetric": False,
    },
    "HAS_HEALTH_FACT": {
        "source_type": "Person",
        "target_type": "HealthFact",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "ASPIRES_TO": {
        "source_type": "Person",
        "target_type": "Aspiration",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "PARENT_OF": {
        "source_type": "Person",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "CHILD_OF": {
        "source_type": "Person",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "SPOUSE_OF": {
        "source_type": "Person",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": ["since", "until"],
        "enums": {},
        "symmetric": True,
    },
    "SIBLING_OF": {
        "source_type": "Person",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": True,
    },
    "FRIEND_OF": {
        "source_type": "Person",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": ["since", "context"],
        "enums": {},
        "symmetric": True,
    },
    "MEMBER_OF": {
        "source_type": "Person",
        "target_type": "Organization",
        "required_attrs": [],
        "optional_attrs": ["role", "title", "since", "until"],
        "enums": {},
        "symmetric": False,
    },
    "OWNED_BY": {
        "source_type": "Mind",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "CREATED_BY": {
        "source_type": "Mind",
        "target_type": "Person",
        "required_attrs": [],
        "optional_attrs": ["since"],
        "enums": {},
        "symmetric": False,
    },
    "HAS_SKILL": {
        "source_type": "Mind",
        "target_type": "Skill",
        "required_attrs": [],
        "optional_attrs": ["last_used"],
        "enums": {},
        "symmetric": False,
    },
    "HAS_TOOL": {
        "source_type": "Mind",
        "target_type": "Tool",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "RUNS_AS": {
        "source_type": "Mind",
        "target_type": "Runtime",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    "EMBODIES": {
        "source_type": "Mind",
        "target_type": "SoulValue",
        "required_attrs": [],
        "optional_attrs": [],
        "enums": {},
        "symmetric": False,
    },
    # ---- Device edges ----
    "OWNS": {
        "source_type": "Person",
        "target_type": "Device",
        "required_attrs": [],
        "optional_attrs": ["since"],
        "enums": {},
        "symmetric": False,
    },
    "RUNS": {
        "source_type": "Device",
        "target_type": "OS",
        "required_attrs": [],
        "optional_attrs": ["since"],
        "enums": {},
        "symmetric": False,
    },
    "HAS_INSTALLED": {
        "source_type": "Device",
        "target_type": "Software",
        "required_attrs": [],
        "optional_attrs": ["since"],
        "enums": {},
        "symmetric": False,
    },
}


def validate_node(
    entity_type: str, properties: dict
) -> tuple[bool, str | None, dict | None]:
    """Validate a node write against the schema.

    Returns (ok, code, detail_dict). On failure, code is one of:
        unknown_node_type, missing_required, unknown_field, invalid_enum
    On success returns (True, None, None).
    """
    spec = SCHEMA_TYPES.get(entity_type)
    if spec is None:
        return False, "unknown_node_type", {
            "detail": f"entity_type {entity_type!r} is not in the schema allow-list",
            "valid_types": sorted(SCHEMA_TYPES.keys()),
        }

    allowed = set(spec["required"]) | set(spec["optional"])
    # Identity / infrastructure fields tolerated and ignored by validation —
    # the write path owns them.
    INFRA = {"id", "agent_id", "created_at", "updated_at", "type", "name"}

    for field in spec["required"]:
        if field == "name":
            # name is column-level on the node row; required for all types.
            continue
        if field not in properties:
            return False, "missing_required", {
                "detail": f"property {field!r} is required for {entity_type}",
                "required": spec["required"],
            }

    for field in properties:
        if field in INFRA:
            continue
        if field not in allowed:
            return False, "unknown_field", {
                "detail": f"property {field!r} is not part of the {entity_type} schema",
                "allowed": sorted(allowed),
            }

    for field, allowed_values in spec.get("enums", {}).items():
        if field in properties and properties[field] not in allowed_values:
            return False, "invalid_enum", {
                "detail": f"{field}={properties[field]!r} not in allowed values for {entity_type}",
                "allowed_values": allowed_values,
            }

    return True, None, None


def validate_edge(
    relation: str,
    source_type: str,
    target_type: str,
    attrs: dict | None = None,
) -> tuple[bool, str | None, dict | None]:
    """Validate an edge write against the schema.

    Returns (ok, code, detail_dict). On failure, code is one of:
        unknown_edge_type, invalid_edge_direction, missing_required_attr,
        unknown_attr, invalid_enum
    """
    attrs = attrs or {}
    spec = SCHEMA_EDGES.get(relation)
    if spec is None:
        return False, "unknown_edge_type", {
            "detail": f"relation {relation!r} is not in the schema allow-list",
            "valid_edges": sorted(SCHEMA_EDGES.keys()),
        }

    if source_type != spec["source_type"] or target_type != spec["target_type"]:
        return False, "invalid_edge_direction", {
            "detail": (
                f"edge {relation} requires {spec['source_type']} → "
                f"{spec['target_type']}, got {source_type} → {target_type}"
            ),
            "expected_source": spec["source_type"],
            "expected_target": spec["target_type"],
        }

    allowed_attrs = set(spec["required_attrs"]) | set(spec["optional_attrs"])

    for attr in spec["required_attrs"]:
        if attr not in attrs:
            return False, "missing_required_attr", {
                "detail": f"attr {attr!r} is required for {relation}",
                "required_attrs": spec["required_attrs"],
            }

    for attr in attrs:
        if attr not in allowed_attrs:
            return False, "unknown_attr", {
                "detail": f"attr {attr!r} is not part of the {relation} schema",
                "allowed": sorted(allowed_attrs),
            }

    for attr, allowed_values in spec.get("enums", {}).items():
        if attr in attrs and attrs[attr] not in allowed_values:
            return False, "invalid_enum", {
                "detail": f"{attr}={attrs[attr]!r} not in allowed values for {relation}",
                "allowed_values": allowed_values,
            }

    return True, None, None


def seed_schema_tables(conn) -> None:
    """Insert hardcoded schema into schema_types + schema_edges tables.

    Idempotent: uses INSERT OR IGNORE keyed on `name`. Existing rows
    (possibly added later via /schema/types or /schema/edges admin
    endpoints) are preserved.
    """
    import json
    import time

    now = time.time()

    for name, spec in SCHEMA_TYPES.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_types
                (name, kind, property_schema, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, spec["kind"], json.dumps(spec), now),
        )

    for name, spec in SCHEMA_EDGES.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_edges
                (name, source_type, target_type, attr_schema, symmetric, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                spec["source_type"],
                spec["target_type"],
                json.dumps(spec),
                1 if spec["symmetric"] else 0,
                now,
            ),
        )

    conn.commit()


def all_types_from_db(conn) -> list[dict]:
    """Read every row from schema_types. Returns parsed dicts."""
    import json

    rows = conn.execute(
        "SELECT name, kind, property_schema FROM schema_types ORDER BY name"
    ).fetchall()
    return [
        {"name": r["name"], "kind": r["kind"], "schema": json.loads(r["property_schema"])}
        for r in rows
    ]


def all_edges_from_db(conn) -> list[dict]:
    """Read every row from schema_edges. Returns parsed dicts."""
    import json

    rows = conn.execute(
        "SELECT name, source_type, target_type, attr_schema, symmetric "
        "FROM schema_edges ORDER BY name"
    ).fetchall()
    return [
        {
            "name": r["name"],
            "source_type": r["source_type"],
            "target_type": r["target_type"],
            "schema": json.loads(r["attr_schema"]),
            "symmetric": bool(r["symmetric"]),
        }
        for r in rows
    ]
