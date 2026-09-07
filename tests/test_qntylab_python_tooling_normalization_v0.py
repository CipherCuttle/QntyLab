"""C4 contract tests: QNTYLAB_PYTHON_TOOLING_NORMALIZATION_V0 (PYTHON_TOOLING_NORMALIZATION_V0).

Bounded structural inspection of the C4 Python tooling normalization —
NO packaging, NO install path, NO dependency changes.

Enforces (per the frozen C4 contract):
1. TOOL_CONFIG_ONLY — root pyproject.toml exists and parses as valid TOML.
2. NO PACKAGING — no [project] table, no [build-system] table, and no
   packaging/publishing metadata (name/version/entry points/build backend).
3. NO-OP PYTEST REGISTRATION — [tool.pytest.ini_options] contains only
   addopts = "" (empty addopts equals the pytest default), so pytest
   semantics are unchanged from baseline.
4. CONFIGFILE REGISTRATION — the running pytest session resolves
   pyproject.toml as its configuration file, proving the canonical
   `python -m pytest -q` command now reads tool configuration from
   pyproject.toml.
5. TOOL SURFACE BOUND — no other [tool.*] tables are declared.

C4 is tool configuration only; this file asserts structure, not runtime
authority, and grants no research/evaluation/execution/claim/trading rights.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_c4_pyproject_exists_and_parses() -> None:
    assert PYPROJECT.is_file()
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    assert isinstance(data, dict)


def test_c4_pyproject_has_no_packaging_tables() -> None:
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    assert "project" not in data
    assert "build-system" not in data


def test_c4_pytest_table_is_explicit_noop() -> None:
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    assert "pytest" in data["tool"]
    assert "ini_options" in data["tool"]["pytest"]
    assert data["tool"]["pytest"]["ini_options"] == {"addopts": ""}


def test_c4_pyproject_is_the_active_pytest_configfile(
    request: object,
) -> None:
    configfile = getattr(getattr(request, "config"), "inifile")
    assert Path(str(configfile)) == PYPROJECT


def test_c4_tool_surface_is_bounded() -> None:
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    assert set(data["tool"]) == {"pytest"}
