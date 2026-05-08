"""SPA-2 — Render build pipeline.

`scripts/build.sh` is what `render.yaml` invokes to produce a
deployable bundle: it installs Python deps, drops a Node binary
into the active Python prefix via `nodeenv`, then runs `npm ci +
npm run build` to emit `frontend/dist/`.

A full execution touches the network (downloads Node + npm deps)
so it's not a good fit for CI. These tests pin the contract that
the build script is wired up correctly:

  • scripts/build.sh exists, is executable, and references
    nodeenv (so deploy doesn't silently regress to Python-only)
  • render.yaml's buildCommand actually invokes scripts/build.sh
    (a developer who runs `pip install -r requirements.txt` by
    hand would skip the SPA otherwise)
  • Node version pinned in build.sh matches package.json's
    engines.node minimum (so dev + Render agree)
  • frontend/package.json declares engines.node >= 22.12 (Vite 8
    requires it)
"""
import json
import os
import re
import stat
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SH  = REPO_ROOT / "scripts" / "build.sh"
RENDER    = REPO_ROOT / "render.yaml"
PKG_JSON  = REPO_ROOT / "frontend" / "package.json"


def test_build_sh_exists_and_executable():
    assert BUILD_SH.exists(), f"missing {BUILD_SH}"
    mode = BUILD_SH.stat().st_mode
    assert mode & stat.S_IXUSR, (
        f"{BUILD_SH} must be executable (chmod +x)"
    )


def test_build_sh_references_nodeenv():
    """`nodeenv` is the Python-side hook that drops Node onto PATH
    inside Render's Python service. If a refactor strips it, prod
    builds fall back to "Node not found" and the SPA stops shipping."""
    body = BUILD_SH.read_text()
    assert "nodeenv" in body, (
        "scripts/build.sh must invoke nodeenv to install Node on Render"
    )
    assert "npm ci" in body, (
        "scripts/build.sh must use `npm ci` (deterministic from "
        "package-lock) — `npm install` would let the lock drift"
    )
    assert "npm run build" in body


def test_build_sh_node_version_satisfies_engines():
    """Pinned Node version in build.sh must satisfy
    `engines.node` in package.json. Otherwise prod builds with a
    Node that Vite refuses to run on."""
    body = BUILD_SH.read_text()
    m = re.search(r'NODE_VERSION="([0-9.]+)"', body)
    assert m, "scripts/build.sh must set NODE_VERSION='X.Y.Z'"
    node_version = tuple(int(p) for p in m.group(1).split("."))

    pkg = json.loads(PKG_JSON.read_text())
    engines = pkg.get("engines", {}).get("node", "")
    em = re.search(r"(\d+)\.(\d+)\.(\d+)", engines)
    assert em, f"frontend/package.json engines.node missing: {engines!r}"
    min_engine = (int(em.group(1)), int(em.group(2)), int(em.group(3)))

    assert node_version >= min_engine, (
        f"build.sh pins Node {node_version} but package.json "
        f"requires >= {min_engine}"
    )


def test_render_buildcommand_runs_build_sh():
    """render.yaml's buildCommand has to actually invoke our
    script — a refactor back to `pip install -r requirements.txt`
    would silently drop the SPA from prod."""
    body = RENDER.read_text()
    # Match `buildCommand: ...build.sh` allowing `bash ` prefix
    # and `./` or `scripts/` paths.
    m = re.search(r"buildCommand:\s*(.+)", body)
    assert m, "render.yaml: no buildCommand line"
    cmd = m.group(1).strip()
    assert "scripts/build.sh" in cmd, (
        f"render.yaml buildCommand must invoke scripts/build.sh; "
        f"got {cmd!r}"
    )


def test_pkg_json_pins_engines_node_22_12_or_newer():
    pkg = json.loads(PKG_JSON.read_text())
    engines = pkg.get("engines", {}).get("node", "")
    em = re.search(r"(\d+)\.(\d+)", engines)
    assert em, f"engines.node must be set; got {engines!r}"
    major, minor = int(em.group(1)), int(em.group(2))
    assert (major, minor) >= (22, 12), (
        f"Vite 8 needs Node 22.12+; engines.node is {engines!r}"
    )
