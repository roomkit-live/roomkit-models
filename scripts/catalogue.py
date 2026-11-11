"""Validate the independent catalogue and publish its static, versioned API."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from comparison import differences

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "data/catalog.json"
ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


def require(condition: bool, message: str) -> None:
    """Fail the build on an invalid catalogue, without quietly dropping entries."""
    if not condition:
        raise ValueError(message)


def https_url(value: object) -> bool:
    """Only web sources may become clickable links in the browser."""
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username


def positive(value: object) -> bool:
    """Unknown limits use null; zero and booleans are not token capacities."""
    return type(value) is int and value > 0


def check_pricing(pricing: object, key: str) -> None:
    if pricing is None:
        return
    require(isinstance(pricing, dict), f"{key}: invalid pricing")
    for field in ("input_per_million", "output_per_million"):
        require(pricing.get(field) is not None, f"{key}: missing {field}")
    for field, value in pricing.items():
        if "per_million" in field:
            require(value is None or (type(value) in (int, float)
                    and math.isfinite(value) and value >= 0), f"{key}: invalid {field}")
        if "multiplier" in field:
            require(type(value) in (int, float) and math.isfinite(value) and value > 0,
                    f"{key}: invalid {field}")
    threshold = pricing.get("long_context_threshold_tokens")
    require(threshold is None or positive(threshold), f"{key}: invalid long-context threshold")
    require(pricing.get("currency") == "USD", f"{key}: unsupported currency")
    date.fromisoformat(pricing["verified"])


def check_guidance(guidance: object, key: str) -> None:
    if guidance is None:
        return
    require(isinstance(guidance, dict), f"{key}: invalid guidance")
    for field in ("summary", "basis"):
        require(isinstance(guidance.get(field), str) and guidance[field].strip(),
                f"{key}: guidance needs {field}")
    for field in ("recommended_for", "limitations"):
        require(isinstance(guidance.get(field), list)
                and all(isinstance(x, str) for x in guidance[field]), f"{key}: invalid {field}")
    require(bool(guidance.get("sources")) and all(https_url(x) for x in guidance["sources"]),
            f"{key}: guidance needs sources")
    date.fromisoformat(guidance["reviewed_on"])


def check_entry(entry: dict, providers: dict) -> None:
    provider, model = entry.get("provider"), entry.get("model", {})
    require(provider in providers, "Unknown provider")
    model_id = model.get("id")
    require(isinstance(model_id, str) and 0 < len(model_id) <= 256
            and not any(ord(c) < 32 for c in model_id), "Invalid model ID")
    key = f"{provider}/{model_id}"
    require(model.get("context_window") is None or positive(model["context_window"]),
            f"{key}: invalid context window")
    require(model.get("supports_vision") is None or type(model["supports_vision"]) is bool,
            f"{key}: invalid vision flag")
    require(type(model.get("deprecated")) is bool, f"{key}: invalid lifecycle")
    require(isinstance(model.get("capabilities"), list)
            and all(isinstance(x, str) for x in model["capabilities"]), f"{key}: invalid tags")
    require(model.get("display_name") is None or isinstance(model["display_name"], str),
            f"{key}: invalid display name")
    require(https_url(entry.get("source")), f"{key}: invalid source")
    require(entry.get("pricing_basis", "provider") in ("provider", "reference"),
            f"{key}: invalid pricing basis")
    if entry.get("pricing_basis") == "reference":
        require(isinstance(entry.get("pricing_note"), str) and bool(entry["pricing_note"]),
                f"{key}: a reference price needs an explanation")
    check_pricing(model.get("pricing"), key)
    check_guidance(entry.get("guidance"), key)
    enrichment = entry.get("upstream")
    require(enrichment is None or isinstance(enrichment, dict), f"{key}: invalid upstream")
    if enrichment is not None:
        require(https_url(enrichment.get("source")), f"{key}: invalid upstream source")
        require(isinstance(enrichment.get("model"), dict), f"{key}: missing upstream record")
        datetime.fromisoformat(enrichment["retrieved_at"])


def validate(data: dict) -> None:
    require(data.get("schema_version") == 1, "Unsupported catalogue schema")
    providers = data.get("providers")
    require(isinstance(providers, dict) and bool(providers), "Missing providers")
    for key, provider in providers.items():
        require(bool(ID.fullmatch(key)), "Invalid provider ID")
        require(isinstance(provider.get("name"), str) and bool(provider["name"]), "Missing provider name")
        require(https_url(provider.get("source")), "Invalid provider source")
    require(isinstance(data.get("models"), list) and bool(data["models"]), "Missing models")
    seen = set()
    for entry in data["models"]:
        check_entry(entry, providers)
        key = (entry["provider"], entry["model"]["id"])
        require(key not in seen, f"Duplicate model: {key}")
        seen.add(key)
    date.fromisoformat(data["updated_on"])


def read(path: Path = CATALOGUE) -> dict:
    data = json.loads(path.read_text())
    validate(data)
    return data


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(data))


def build(data: dict, destination: Path = ROOT / "dist") -> dict:
    """Emit only the site and public data; never publish a repository checkout."""
    validate(data)
    data = copy.deepcopy(data)
    for entry in data["models"]:
        if entry.get("upstream"):
            entry["upstream"]["differences"] = differences(
                entry["provider"], entry["model"], entry["upstream"]["model"],
                compare_prices=entry.get("pricing_basis") != "reference")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(ROOT / "site", destination)
    payload = encoded(data)
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {"schema_version": 1, "catalogue": "catalog.json", "sha256": digest,
                "updated_on": data["updated_on"], "models": len(data["models"])}
    write_json(destination / "v1/catalog.json", data)
    write_json(destination / "v1/manifest.json", manifest)
    for provider in data["providers"]:
        models = [e["model"] for e in data["models"] if e["provider"] == provider]
        write_json(destination / f"v1/roomkit/{provider}.json", models)
    shutil.copy(ROOT / "LICENSE", destination / "LICENSE.txt")
    shutil.copy(ROOT / "NOTICE", destination / "NOTICE.txt")
    (destination / ".nojekyll").touch()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "build"))
    args = parser.parse_args()
    data = read()
    if args.command == "build":
        print(json.dumps(build(data)))
    else:
        print(f"Valid: {len(data['models'])} models across {len(data['providers'])} providers")


if __name__ == "__main__":
    main()
