"""Each packaged dictionary's ``x-version`` is locked to its content (issue #25).

``dictionary_versions.json`` maps name -> x-version -> SHA-256 of the YAML text
without its ``x-version`` line. A content change must come with a new version and
a new line in that file, so two pull requests that bump one dictionary to the same
version collide there instead of merging into one version with two contents.
"""

from __future__ import annotations

import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path

import pytest

LOCK = Path(__file__).with_name("dictionary_versions.json")
_VERSION_LINE = re.compile(r"^x-version:[^\n]*\n", re.MULTILINE)


def _packaged() -> dict[str, str]:
    return {
        p.name.removesuffix(".yaml"): p.read_text(encoding="utf-8")
        for p in files("omnisus.data.dicionarios").iterdir()
        if p.name.endswith(".yaml")
    }


def _version_and_hash(text: str) -> tuple[str, str]:
    (line,) = _VERSION_LINE.findall(text)
    version = line.removeprefix("x-version:").strip().strip("\"'")
    content = _VERSION_LINE.sub("", text)
    return version, hashlib.sha256(content.encode("utf-8")).hexdigest()


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


LOCKED: dict[str, dict[str, str]] = json.loads(LOCK.read_text(encoding="utf-8"))
PACKAGED = _packaged()


def test_every_packaged_dictionary_is_locked_and_nothing_else():
    assert sorted(LOCKED) == sorted(PACKAGED)


@pytest.mark.parametrize("name", sorted(PACKAGED))
def test_content_matches_the_hash_locked_for_its_version(name):
    version, digest = _version_and_hash(PACKAGED[name])
    locked = LOCKED.get(name, {})
    assert version in locked, (
        f'{name} {version} is not in {LOCK.name}; add "{version}": "{digest}"'
    )
    assert locked[version] == digest, (
        f"{name} changed under x-version {version}: raise x-version and add "
        f'"<new version>": "{digest}" to {LOCK.name}'
    )


@pytest.mark.parametrize("name", sorted(PACKAGED))
def test_current_version_is_the_highest_locked(name):
    version, _ = _version_and_hash(PACKAGED[name])
    assert max(LOCKED.get(name, {version: ""}), key=_semver) == version
