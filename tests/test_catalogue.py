"""Contract and publication tests without a provider, credentials or network."""

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from catalogue import build, check_guidance, read, validate
from comparison import differences
from upstream import compare, lookup, markdown, reviewed_differences, selected, validate_upstream


def fixture():
    return {"schema_version": 1, "updated_on": "2026-11-11", "providers": {
        "anthropic": {"name": "Example", "source": "https://example.com/models"}}, "models": [{
            "provider": "anthropic", "source": "https://example.com/models",
            "model": {"id": "model-a", "display_name": "Model A", "context_window": 100,
                      "supports_vision": None, "deprecated": False, "capabilities": [],
                      "pricing": {"input_per_million": 2, "output_per_million": 10,
                                  "verified": "2026-11-10", "currency": "USD"}},
            "guidance": None, "upstream": None}]}


class CatalogueTests(unittest.TestCase):
    def test_real_catalogue_has_no_duplicate_or_invalid_entries(self):
        validate(read())

    def test_publication_has_a_verifiable_payload_and_unchanged_roomkit_shape(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "site"
            manifest = build(data, root)
            payload = (root / "v1/catalog.json").read_bytes()
            self.assertEqual(manifest["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(json.loads((root / "v1/roomkit/anthropic.json").read_text()),
                             [data["models"][0]["model"]])
            self.assertTrue((root / "index.html").is_file())
            self.assertFalse((root / "scripts").exists())
            self.assertFalse((root / "data").exists())
            self.assertEqual(build(data, root), manifest)

    def test_duplicate_and_unknown_provider_fail(self):
        data = fixture()
        data["models"].append(copy.deepcopy(data["models"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate(data)
        data = fixture()
        data["models"][0]["provider"] = "missing"
        with self.assertRaisesRegex(ValueError, "Unknown provider"):
            validate(data)

    def test_unsafe_links_and_invalid_prices_fail(self):
        for price in (None, -1, float("nan"), float("inf"), True):
            with self.subTest(price=price):
                data = fixture()
                data["models"][0]["model"]["pricing"]["input_per_million"] = price
                with self.assertRaises(ValueError):
                    validate(data)
        data = fixture()
        data["models"][0]["source"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "source"):
            validate(data)

    def test_long_context_pricing_preserves_roomkit_constraints(self):
        for field, value in (("long_context_threshold_tokens", -1),
                             ("long_context_threshold_tokens", 0),
                             ("long_context_input_multiplier", None),
                             ("long_context_output_multiplier", 0)):
            data = fixture()
            data["models"][0]["model"]["pricing"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate(data)

    def test_unknown_is_not_zero_or_false(self):
        data = fixture()
        model = data["models"][0]["model"]
        model.update(context_window=None, supports_vision=None, pricing=None)
        validate(data)
        model["context_window"] = 0
        with self.assertRaisesRegex(ValueError, "context"):
            validate(data)

    def test_guidance_needs_evidence_and_a_review_date(self):
        with self.assertRaises(ValueError):
            check_guidance({"summary": "Best model"}, "example")
        guidance = {"summary": "Suitable for a measured task", "basis": "A reproducible evaluation",
                    "recommended_for": ["Small changes"], "limitations": [],
                    "sources": ["https://example.com/evaluation"], "reviewed_on": "2026-11-11"}
        check_guidance(guidance, "example")


class UpstreamTests(unittest.TestCase):
    def test_another_sellers_reference_price_is_not_compared_as_the_offer(self):
        model = {"id": "example", "context_window": 100, "pricing": {"input_per_million": 5}}
        remote = {"limit": {"context": 200}, "cost": {"input": 1}}
        self.assertEqual(differences("openrouter", model, remote, compare_prices=False),
                         [["context", 100, 200]])

    def test_google_cache_write_compares_the_full_charge_on_openrouter(self):
        model = {"id": "google/example", "pricing": {"cache_write_per_million": 0.7916667}}
        remote = {"cost": {"input": 0.75, "cache_write": 0.041667}}
        self.assertEqual(differences("openrouter", model, remote), [])
        remote["cost"]["cache_write"] = 0.1
        self.assertEqual(differences("openrouter", model, remote)[0][2], 0.85)
        self.assertEqual(differences("another-host", model, remote)[0][2], 0.1)

    def test_invalid_or_empty_upstream_is_not_a_successful_check(self):
        for data in ({}, {"error": "Unavailable"}, {"anthropic": {"models": {}}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_upstream(data)

    def test_previously_reviewed_out_of_scope_models_are_not_new_every_day(self):
        upstream = {"anthropic": {"models": {
            "old": {"id": "old", "modalities": {"output": ["text"]}},
            "new": {"id": "new", "modalities": {"output": ["text"]}}}}}
        report = compare(fixture(), upstream, {"anthropic": ["old"]})
        self.assertEqual(report["new"], ["anthropic/new"])

    def test_host_and_identifier_must_both_match(self):
        entry = fixture()["models"][0]
        other_host = {"openai": {"models": {"model-a": {"id": "model-a"}}}}
        self.assertIsNone(lookup(entry, other_host))
        dated = {"anthropic": {"models": {"model-a-20261111": {"id": "model-a-20261111"}}}}
        self.assertIsNone(lookup(entry, dated))

    def test_verification_reports_changes_and_never_updates_the_catalogue(self):
        data = fixture()
        before = copy.deepcopy(data)
        remote = {"id": "model-a", "limit": {"context": 200}, "cost": {"input": 3}}
        upstream = {"anthropic": {"models": {"model-a": remote, "new": {
            "id": "new", "modalities": {"output": ["text"]}}}}}
        report = compare(data, upstream)
        self.assertEqual(data, before)
        self.assertEqual(report["changed"], ["anthropic/model-a"])
        self.assertEqual(report["new"], ["anthropic/new"])
        self.assertEqual(report["drift"][0]["differences"], ["context: 100 → 200", "input_per_million: 2 → 3"])
        data["models"][0]["upstream"] = {"model": selected(remote)}
        self.assertEqual(compare(data, upstream)["changed"], [])

    def test_missing_data_is_coverage_not_retirement(self):
        report = compare(fixture(), {})
        self.assertEqual(report["unmatched"], ["anthropic/model-a"])
        self.assertEqual(report["changed"], [])
        self.assertEqual(reviewed_differences(fixture()["models"][0]["model"], {}), [])

    def test_reports_escape_untrusted_identifiers(self):
        report = {"checked_at": "today", "source_sha256": "a" * 64, "changed": ["<img>\ntext"],
                  "drift": [], "unmatched": [], "new": []}
        result = markdown(report)
        self.assertNotIn("<img>", result)
        self.assertIn("&lt;img&gt; text", result)


if __name__ == "__main__":
    unittest.main()
