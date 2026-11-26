"""A03 Software Supply Chain Failures: everything is pinned and hash-locked. The CI
pipeline additionally runs pip-audit, npm audit and Trivy, and fails on any finding."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


def _lock_entries(path: Path) -> dict[str, list[str]]:
    entries: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        m = re.match(r"^([A-Za-z0-9_.\-\[\],]+)==([^\s\\;]+)", s)
        if m:
            current = m.group(1).split("[")[0].lower()
            entries[current] = []
        elif s.startswith("--hash=sha256:") and current:
            entries[current].append(s.split(":", 1)[1].rstrip(" \\"))
        elif s and not s.startswith("#") and not s.startswith("--hash") and not line.startswith(" "):
            pytest.fail(f"{path.name}: unpinned or unexpected line: {s!r}")
    return entries


@pytest.mark.parametrize("lock", ["requirements.lock", "requirements-dev.lock"])
def test_every_dependency_is_pinned_with_hashes(lock):
    entries = _lock_entries(BACKEND / lock)
    assert entries, f"{lock} is empty"
    for name, hashes in entries.items():
        assert hashes, f"{lock}: {name} has no --hash"
        assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes), name


def test_every_direct_dependency_is_locked():
    locked = _lock_entries(BACKEND / "requirements.lock")
    for line in (BACKEND / "requirements.in").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name = re.split(r"[\[<>=!~ ]", line, maxsplit=1)[0].lower()
        assert name in locked, f"{name} is in requirements.in but not in requirements.lock"


def test_container_base_images_pinned_by_digest():
    dockerfiles = list((REPO / "deployment").glob("Dockerfile*"))
    assert dockerfiles, "no Dockerfiles found"
    for f in dockerfiles:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().upper().startswith("FROM "):
                image = line.split()[1]
                assert "@sha256:" in image, f"{f.name}: base image not pinned by digest: {line.strip()}"


def test_compose_images_pinned_by_digest():
    compose = (REPO / "deployment" / "compose.yaml").read_text(encoding="utf-8")
    for m in re.finditer(r"^\s*image:\s*(\S+)", compose, re.MULTILINE):
        image = m.group(1)
        if image.startswith("${"):
            continue  # the app's own images, built by CI and pinned at release
        assert "@sha256:" in image, f"compose.yaml: {image} not pinned by digest"


def test_frontend_lockfile_present_and_integrity_checked():
    lock = REPO / "frontend" / "package-lock.json"
    assert lock.exists(), "frontend/package-lock.json missing"
    data = json.loads(lock.read_text(encoding="utf-8"))
    packages = {k: v for k, v in data.get("packages", {}).items() if k and not v.get("link")}
    assert packages
    missing = [k for k, v in packages.items() if not v.get("integrity", "").startswith("sha512-")]
    assert not missing, f"packages without sha512 integrity: {missing[:5]}"
    resolved = {v.get("resolved", "") for v in packages.values()}
    assert all(r.startswith("https://registry.npmjs.org/") for r in resolved if r), "non-registry package source"


def test_frontend_dependencies_are_exact_versions():
    pkg = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name, ver in pkg.get(section, {}).items():
            assert re.fullmatch(r"\d+\.\d+\.\d+(-[\w.]+)?", ver), f"{name}@{ver} is not an exact version"
