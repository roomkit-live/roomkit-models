"""Compare models.dev with the reviewed catalogue; never change published data."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from catalogue import ROOT, encoded, read
from comparison import differences

URL = "https://models.dev/api.json"
MAX_BYTES = 32 * 1024 * 1024
# Same host only: matching a model's name across hosts would mix their prices.
PROVIDERS = {"anthropic": "anthropic", "openai": "openai", "gemini": "google",
             "mistral": "mistral", "xai": "xai", "meta": "meta", "deepseek": "deepseek",
             "qwen": "alibaba", "minimax": "minimax", "kimi": "moonshotai",
             "cerebras": "cerebras", "openrouter": "openrouter"}
FIELDS = ("id", "name", "description", "canonical_model_id", "family", "attachment",
          "reasoning", "reasoning_options", "tool_call", "structured_output",
          "temperature", "knowledge", "release_date", "last_updated", "modalities",
          "open_weights", "limit", "cost", "status", "benchmarks")


def fetch() -> tuple[dict, str]:
    request = urllib.request.Request(URL, headers={"User-Agent": "roomkit-models/0.1",
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("models.dev response exceeds 32 MiB")
    data = json.loads(body)
    validate_upstream(data)
    return data, hashlib.sha256(body).hexdigest()


def validate_upstream(data: object) -> None:
    """An HTTP 200 with an error object is not a successful verification."""
    if not isinstance(data, dict) or not data:
        raise ValueError("models.dev returned no provider catalogue")
    for provider, record in data.items():
        if not isinstance(record, dict) or not isinstance(record.get("models"), dict):
            raise ValueError(f"Invalid provider catalogue: {provider}")
        for model_id, model in record["models"].items():
            if not isinstance(model, dict) or model.get("id") != model_id:
                raise ValueError(f"Invalid model record: {provider}/{model_id}")
    if not any(record["models"] for record in data.values()):
        raise ValueError("models.dev returned no models")


def selected(model: dict) -> dict:
    return {key: model[key] for key in FIELDS if key in model}


def lookup(entry: dict, upstream: dict) -> dict | None:
    provider = PROVIDERS.get(entry["provider"])
    if not provider:
        return None
    # Exact model IDs only. Missing aliases are reported, never guessed.
    return upstream.get(provider, {}).get("models", {}).get(entry["model"]["id"])


def reviewed_differences(model: dict, remote: dict, provider: str = "", *, compare_prices: bool = True) -> list[str]:
    """Compare equivalent units and the same host, leaving unknowns explicit."""
    return [f"{field}: {before} → {after}" for field, before, after in differences(
        provider, model, remote, compare_prices=compare_prices)]


def compare(data: dict, upstream: dict, baseline: dict | None = None) -> dict:
    result = {"changed": [], "unmatched": [], "new": [], "drift": []}
    known: dict[str, set[str]] = {}
    for entry in data["models"]:
        provider, model = entry["provider"], entry["model"]
        known.setdefault(provider, set()).add(model["id"])
        key = f"{provider}/{model['id']}"
        remote = lookup(entry, upstream)
        if remote is None:
            result["unmatched"].append(key)
            continue
        if selected(remote) != (entry.get("upstream") or {}).get("model"):
            result["changed"].append(key)
        changes = reviewed_differences(model, remote, provider,
                                      compare_prices=entry.get("pricing_basis") != "reference")
        if changes:
            result["drift"].append({"model": key, "differences": changes})
    for provider, ids in known.items():
        remote = upstream.get(PROVIDERS.get(provider, ""), {}).get("models", {})
        observed = set((baseline or {}).get(provider, ids))
        result["new"].extend(f"{provider}/{model}" for model in sorted(remote.keys() - observed)
                             if "text" in remote[model].get("modalities", {}).get("output", []))
    return result


def safe(value: str) -> str:
    """Keep upstream identifiers as report text, not Markdown or HTML."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("`", "\\`").replace("\n", " ")


def markdown(report: dict) -> str:
    lines = ["# Daily catalogue verification", "", f"Checked: {report['checked_at']}",
             f"Source: {URL}", f"SHA-256: `{report['source_sha256']}`", "",
             "This report does not change the published catalogue. Confirm differences against the provider's documentation.",
             "Legacy reference prices from another seller are excluded from price comparisons. OpenRouter/Google cache writes include ordinary input before comparison.",
             "Unmatched entries are coverage gaps, not evidence of retirement. New IDs are compared with the last reviewed upstream inventory."]
    labels = {"changed": "Upstream metadata changed", "drift": "Reviewed facts differ",
              "unmatched": "No exact upstream match", "new": "New upstream text model IDs"}
    for category, label in labels.items():
        entries = report[category]
        lines.extend(["", f"## {label} ({len(entries)})", ""])
        for entry in entries:
            text = entry if isinstance(entry, str) else entry["model"] + ": " + "; ".join(entry["differences"])
            lines.append("- " + safe(text))
        if not entries:
            lines.append("None.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Use a downloaded fixture instead of the network")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/upstream.md")
    args = parser.parse_args()
    data = read()
    if args.source:
        raw = args.source.read_bytes()
        upstream, digest = json.loads(raw), hashlib.sha256(raw).hexdigest()
        validate_upstream(upstream)
    else:
        upstream, digest = fetch()
    lock = json.loads((ROOT / "data/upstream-lock.json").read_text())
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "source_sha256": digest,
              **compare(data, upstream, lock.get("known_ids"))}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown(report))
    args.report.with_suffix(".json").write_bytes(encoded(report))
    print(json.dumps({key: len(report[key]) for key in ("changed", "drift", "unmatched", "new")}))


if __name__ == "__main__":
    main()
