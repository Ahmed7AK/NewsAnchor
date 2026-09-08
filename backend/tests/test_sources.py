"""Registry loading, including how the roster file is located.

sources.yaml lives outside the Python package on purpose -- it is
configuration you are meant to edit, not code -- so it has to be *found*.
Getting that wrong broke `pip install .` with an error that named a path
inside site-packages and told the user nothing useful.
"""

from __future__ import annotations

import pathlib

import pytest

from newsanchor import sources as src
from newsanchor.sources import RegistryError, active_sources, load_registry


def test_default_registry_loads_and_is_internally_consistent():
    registry = load_registry()
    assert len(registry) > 20
    for source in registry.values():
        assert source.lean is None or source.lean in (-2, -1, 0, 1, 2)
        assert source.id and source.name


def test_env_override_takes_precedence(tmp_path, monkeypatch):
    custom = tmp_path / "mine.yaml"
    custom.write_text(
        "sources:\n  - id: only\n    name: Only Source\n    lean: 0\n"
        "    feeds: ['https://only.example/rss']\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEWSANCHOR_SOURCES", str(custom))
    assert src.resolve_registry_path() == custom
    assert set(load_registry(src.resolve_registry_path())) == {"only"}


def test_repo_checkout_beats_the_bundled_copy():
    """Your edits to data/sources.yaml must win over the packaged default."""
    resolved = src.resolve_registry_path()
    assert "site-packages" not in str(resolved)
    assert resolved.is_file()


def test_missing_registry_error_names_what_it_tried(monkeypatch):
    monkeypatch.delenv("NEWSANCHOR_SOURCES", raising=False)
    monkeypatch.setattr(src, "_PACKAGE_DIR", pathlib.Path("/nonexistent/deep/pkg"))
    with pytest.raises(RegistryError) as excinfo:
        src.resolve_registry_path()
    message = str(excinfo.value)
    assert "Looked in" in message
    assert "NEWSANCHOR_SOURCES" in message, "error must say how to fix it"


def test_shallow_package_path_does_not_crash(monkeypatch):
    """A package installed at a shallow path has no parents[1] to index."""
    monkeypatch.delenv("NEWSANCHOR_SOURCES", raising=False)
    monkeypatch.setattr(src, "_PACKAGE_DIR", pathlib.Path("/"))
    with pytest.raises(RegistryError):
        src.resolve_registry_path()  # RegistryError, not IndexError


def test_invalid_lean_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("sources:\n  - id: x\n    name: X\n    lean: 7\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="lean must be"):
        load_registry(bad)


def test_duplicate_ids_are_rejected(tmp_path):
    dupe = tmp_path / "dupe.yaml"
    dupe.write_text("sources:\n  - id: x\n    name: X\n  - id: x\n    name: Y\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="duplicate source id"):
        load_registry(dupe)


def test_state_affiliated_sources_are_opt_in():
    registry = load_registry()
    state = {s.id for s in registry.values() if s.state_affiliated}
    assert state, "registry should carry some state-affiliated outlets"

    default_ids = {s.id for s in active_sources(registry)}
    assert not (state & default_ids), "state media must be off by default"

    with_state = {s.id for s in active_sources(registry, include_state_affiliated=True)}
    assert state & with_state, "opting in must actually include them"


def test_sources_without_feeds_are_not_polled():
    """Reuters has no fetchable feed; it exists only as a wire signature."""
    registry = load_registry()
    assert registry["reuters"].feeds == ()
    assert "reuters" not in {s.id for s in active_sources(registry)}
