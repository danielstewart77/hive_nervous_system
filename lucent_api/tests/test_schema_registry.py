"""Unit tests for lucent_api.schema_registry validators.

Pure-function tests — no DB, no HTTP. Covers the five validations the
strict upsert endpoint runs before delegating to the write path:
type allow-list, required properties, unknown fields, enum values,
edge type allow-list, edge direction.

Run: python -m unittest lucent_api.tests.test_schema_registry
"""

from __future__ import annotations

import unittest

from lucent_api.schema_registry import validate_edge, validate_node


class ValidateNodeTests(unittest.TestCase):
    def test_valid_person_passes(self):
        ok, code, detail = validate_node("Person", {"first_name": "Daniel"})
        self.assertTrue(ok)
        self.assertIsNone(code)
        self.assertIsNone(detail)

    def test_valid_contactmethod_passes(self):
        ok, code, _ = validate_node(
            "ContactMethod", {"kind": "email", "value": "x@y.z", "label": "work"}
        )
        self.assertTrue(ok)
        self.assertIsNone(code)

    def test_unknown_type_rejected(self):
        ok, code, detail = validate_node("Project", {})
        self.assertFalse(ok)
        self.assertEqual(code, "unknown_node_type")
        self.assertIn("Person", detail["valid_types"])

    def test_missing_required_property_rejected(self):
        # ContactMethod requires both 'kind' and 'value'
        ok, code, _ = validate_node("ContactMethod", {"kind": "email"})
        self.assertFalse(ok)
        self.assertEqual(code, "missing_required")

    def test_unknown_field_rejected(self):
        ok, code, _ = validate_node(
            "Person", {"first_name": "Daniel", "favorite_color": "orange"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, "unknown_field")

    def test_invalid_enum_value_rejected(self):
        ok, code, detail = validate_node(
            "ContactMethod", {"kind": "fax", "value": "555-1234"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, "invalid_enum")
        self.assertIn("email", detail["allowed_values"])

    def test_infrastructure_fields_ignored(self):
        # id, agent_id, created_at, updated_at, type, name are infrastructure
        # — caller may pass them but they don't fail "unknown_field".
        ok, code, _ = validate_node(
            "Person",
            {
                "first_name": "Daniel",
                "agent_id": "skippy",
                "created_at": "2026-05-11",
                "type": "Person",
            },
        )
        self.assertTrue(ok)
        self.assertIsNone(code)

    def test_optional_fields_accepted(self):
        # Aspiration.as_of is optional — present should work, absent should
        # also work because it's not in 'required'.
        ok, _, _ = validate_node("Aspiration", {"summary": "become a chef"})
        self.assertTrue(ok)
        ok, _, _ = validate_node(
            "Aspiration", {"summary": "become a chef", "as_of": "2026-05-11"}
        )
        self.assertTrue(ok)

    def test_valid_education_passes(self):
        ok, _, _ = validate_node(
            "Education", {"level": "4th grade", "school_year": "2025-2026"}
        )
        self.assertTrue(ok)

    def test_education_missing_required_rejected(self):
        ok, code, _ = validate_node("Education", {"level": "4th grade"})
        self.assertFalse(ok)
        self.assertEqual(code, "missing_required")


class ValidateEdgeTests(unittest.TestCase):
    def test_valid_edge_passes(self):
        ok, code, _ = validate_edge("HAS_CONTACT", "Person", "ContactMethod")
        self.assertTrue(ok)
        self.assertIsNone(code)

    def test_unknown_edge_type_rejected(self):
        ok, code, detail = validate_edge("TOTALLY_BOGUS_REL", "Person", "Person")
        self.assertFalse(ok)
        self.assertEqual(code, "unknown_edge_type")
        self.assertIn("HAS_CONTACT", detail["valid_edges"])

    def test_wrong_direction_rejected(self):
        # HAS_CONTACT goes Person → ContactMethod, not the reverse
        ok, code, detail = validate_edge("HAS_CONTACT", "ContactMethod", "Person")
        self.assertFalse(ok)
        self.assertEqual(code, "invalid_edge_direction")
        self.assertEqual(detail["expected_source"], "Person")
        self.assertEqual(detail["expected_target"], "ContactMethod")

    def test_self_referential_edge_passes(self):
        # SPOUSE_OF is Person → Person (symmetric, but direction still valid)
        ok, _, _ = validate_edge("SPOUSE_OF", "Person", "Person")
        self.assertTrue(ok)

    def test_unknown_attr_rejected(self):
        ok, code, _ = validate_edge(
            "HAS_CONTACT", "Person", "ContactMethod", attrs={"weird_attr": True}
        )
        self.assertFalse(ok)
        self.assertEqual(code, "unknown_attr")

    def test_mind_to_skill_edge_passes(self):
        ok, _, _ = validate_edge("HAS_SKILL", "Mind", "Skill")
        self.assertTrue(ok)

    def test_mind_skill_wrong_direction_rejected(self):
        ok, code, _ = validate_edge("HAS_SKILL", "Skill", "Mind")
        self.assertFalse(ok)
        self.assertEqual(code, "invalid_edge_direction")

    def test_has_education_edge_passes(self):
        ok, _, _ = validate_edge("HAS_EDUCATION", "Person", "Education")
        self.assertTrue(ok)

    def test_has_education_wrong_direction_rejected(self):
        ok, code, _ = validate_edge("HAS_EDUCATION", "Education", "Person")
        self.assertFalse(ok)
        self.assertEqual(code, "invalid_edge_direction")


if __name__ == "__main__":
    unittest.main()
