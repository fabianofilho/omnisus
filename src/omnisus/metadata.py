"""Offline, detached metadata resolved from the packaged dictionary resources.

Declared logical/source types never instruct ingestion or imply the physical SQL
schema of a particular snapshot. Analytical applicability is resolved separately.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from importlib.resources import files
from typing import Any

from omnisus.transforms.dictionaries import load_dicionario

SCHEMA_VERSION = "1.0.0"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sources_registry() -> dict[str, Any]:
    """Read canonical packaged sources; callers own the returned object."""
    path = files("omnisus.data.dicionarios") / "sources/registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    ids = [source["id"] for source in registry["sources"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source identifiers")
    return registry


def resolved_codes(definition: dict[str, Any]) -> list[dict[str, str]]:
    """``field.codes`` of a dictionary field: its ``x-decode`` with the authored missing kinds."""
    missing = definition.get("x-metadata", {}).get("missing_codes", {})
    return [
        {
            "value": str(code),
            "label": str(label),
            "missing_kind": missing.get(str(code), "unknown"),
        }
        for code, label in definition.get("x-decode", {}).items()
    ]


def _column(
    dataset: str, version: str, definition: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    authored = definition.get("x-metadata", {})
    name = definition["name"]
    codes = resolved_codes(definition)
    if len({code["value"] for code in codes}) != len(codes):
        raise ValueError(f"Duplicate resolved codes: {dataset}.{name}")
    field = {
        "id": f"{dataset}.{name}",
        "name": name,
        "physical_name": authored.get("physical_name"),
        "label": definition.get("label"),
        "description": definition.get("description"),
        "physical_type": authored.get("physical_type"),
        "logical_type": definition.get("type"),
        "unit": authored.get("unit"),
        "format": definition.get("x-format"),
        "codes": codes,
        "domain": authored.get(
            "domain",
            {"kind": "enum" if codes else "unknown", "completeness": "unknown", "reference": None},
        ),
        "constraints": definition.get("constraints"),
        "relationships": definition.get("foreignKeys", []),
        "derivation": authored.get("derivation"),
    }
    claims = []
    used_sources: set[str] = set()
    authored_claims = {c["target"]: c for c in authored.get("claims", [])}
    if len(authored_claims) != len(authored.get("claims", [])):
        raise ValueError(f"Duplicate claims: {dataset}.{name}")
    for key, value in field.items():
        target = f"/field/{key}"
        digest = hashlib.sha256(canonical_json(value)).hexdigest()
        claim = authored_claims.pop(target, None)
        if claim is None:
            claim = {
                "target": target,
                "value_sha256": digest,
                "status": "unreviewed",
                "checked_at": None,
                "method": None,
                "reviewer": None,
                "evidence": [],
                "note": "Authored metadata; no review inferred.",
            }
        elif claim["value_sha256"] != digest:
            raise ValueError(f"Changed reviewed value: {dataset}.{name} {target}")
        for evidence in claim["evidence"]:
            source_id = evidence["source_id"]
            if source_id not in sources:
                raise ValueError(f"Unresolved source: {source_id}")
            if (
                claim["status"] == "verified_in_source"
                and sources[source_id]["authority"] != "official"
            ):
                raise ValueError("Verified source claim requires official evidence")
            used_sources.add(source_id)
        if claim["status"] == "verified_in_source" and not claim["evidence"]:
            raise ValueError("Verified source claim requires evidence")
        claims.append(claim)
    if authored_claims:
        raise ValueError(f"Unknown claim targets: {sorted(authored_claims)}")
    applicability = authored.get(
        "applicability",
        {
            "status": "unknown",
            "data_period": None,
            "valid_from": None,
            "valid_until": None,
            "conditions": [],
            "reason": "No applicability inferred from a legacy definition.",
            "evidence": [],
        },
    )
    for evidence in applicability.get("evidence", []):
        if evidence["source_id"] not in sources:
            raise ValueError(f"Unresolved source: {evidence['source_id']}")
        used_sources.add(evidence["source_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "dictionary_version": version,
        "dataset": {
            "id": dataset,
            "category": dataset.split("_")[0].upper(),
            "subtype": "unknown",
            "product": dataset,
        },
        "field": field,
        "claims": claims,
        "sources": [sources[key] for key in sorted(used_sources)],
        "applicability": applicability,
        "observations": authored.get("observations", []),
        "issues": authored.get("issues", []),
    }


def describe_dataset(dataset: str) -> dict[str, Any]:
    """A dataset's packaged metadata: fields, sources, analytical rules and a digest.

    Works offline. ``schema.fields`` keeps the authored definitions;
    ``fields`` holds one self-contained document per column with its review state.
    Neither describes a live lake: use ``DESCRIBE`` at the snapshot you query.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``; see :func:`~omnisus.datasets`.

    Returns:
        A new JSON-compatible dict on every call, with ``metadata_hash`` to pin it and
        ``analytics`` (``version``, ``validated_sources``) for the harmonised
        categories.

    Raises:
        FileNotFoundError: ``dataset`` has no packaged dictionary.

    Examples:
        >>> import omnisus as sus
        >>> metadata = sus.describe_dataset("sim_obitos")
        >>> sorted(metadata)[:3]
        ['analytics', 'dataset', 'dictionary_version']
        >>> len(metadata["metadata_hash"])
        64
    """
    dictionary = load_dicionario(dataset)
    raw = deepcopy(dictionary.raw)
    registry = sources_registry()
    sources = {source["id"]: source for source in registry["sources"]}
    analytics = raw.get("x-analytics")
    if analytics:
        for name in ("age", "sex"):
            rule = analytics.get(name)
            if rule is None:
                continue
            if not rule.get("evidence"):
                raise ValueError(f"Analytical rule requires evidence: {name}")
            for evidence in rule["evidence"]:
                source_id = evidence["source_id"]
                if source_id not in sources:
                    raise ValueError(f"Unresolved analytical source: {source_id}")
                if sources[source_id]["authority"] != "official":
                    raise ValueError(f"Analytical rule requires official evidence: {name}")
    result = {
        "schema_version": SCHEMA_VERSION,
        "dataset": dictionary.name,
        "title": dictionary.title,
        "dictionary_version": dictionary.version,
        "schema": raw["schema"],
        "fields": [
            _column(dictionary.name, dictionary.version, field, sources)
            for field in raw["schema"]["fields"]
        ],
        "sources": registry["sources"],
        "analytics": raw.get("x-analytics"),
        "storage": {
            "policy": "source_physical_types",
            "dictionary_types": "descriptive",
            "provenance": "LakeReader.publications()",
            "observed_schema": None,
        },
    }
    used_sources = {source["id"] for column in result["fields"] for source in column["sources"]}
    if analytics:
        for name in ("age", "sex"):
            used_sources.update(
                evidence["source_id"] for evidence in analytics.get(name, {}).get("evidence", [])
            )
    result["sources"] = [sources[key] for key in sorted(used_sources)]
    result["metadata_hash"] = hashlib.sha256(canonical_json(result)).hexdigest()
    return result
