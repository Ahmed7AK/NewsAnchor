"""Loading and querying the source registry (data/sources.yaml)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from .models import Source

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "data" / "sources.yaml"


class RegistryError(ValueError):
    pass


def _coerce(raw: dict) -> Source:
    missing = {"id", "name"} - raw.keys()
    if missing:
        raise RegistryError(f"source entry missing required key(s): {sorted(missing)}")

    lean = raw.get("lean")
    if lean is not None and lean not in (-2, -1, 0, 1, 2):
        raise RegistryError(f"{raw['id']}: lean must be null or an integer in -2..2, got {lean!r}")

    return Source(
        id=raw["id"],
        name=raw["name"],
        homepage=raw.get("homepage", ""),
        feeds=tuple(raw.get("feeds") or ()),
        lean=lean,
        tier=raw.get("tier", "national"),
        country=raw.get("country", "US"),
        paywall=raw.get("paywall"),
        state_affiliated=bool(raw.get("state_affiliated", False)),
        # State-affiliated outlets are opt-in even if `enabled` is unset.
        enabled=bool(raw.get("enabled", not raw.get("state_affiliated", False))),
        notes=(raw.get("notes") or "").strip(),
    )


def load_registry(path: Path | str | None = None) -> dict[str, Source]:
    path = Path(path or os.environ.get("NEWSANCHOR_SOURCES") or DEFAULT_REGISTRY)
    if not path.exists():
        raise RegistryError(f"source registry not found at {path}")

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = doc.get("sources")
    if not entries:
        raise RegistryError(f"{path} contains no `sources:` list")

    registry: dict[str, Source] = {}
    for raw in entries:
        source = _coerce(raw)
        if source.id in registry:
            raise RegistryError(f"duplicate source id: {source.id}")
        registry[source.id] = source
    return registry


@lru_cache(maxsize=1)
def default_registry() -> dict[str, Source]:
    return load_registry()


def active_sources(
    registry: dict[str, Source],
    *,
    include_state_affiliated: bool = False,
    only: set[str] | None = None,
) -> list[Source]:
    """Sources we will actually fetch from this run."""
    out = []
    for source in registry.values():
        if only is not None and source.id not in only:
            continue
        if not source.feeds:
            continue  # e.g. Reuters -- known to us, but nothing to poll
        if source.state_affiliated and not include_state_affiliated:
            continue
        if not source.enabled and not (source.state_affiliated and include_state_affiliated):
            continue
        out.append(source)
    return out


def spectrum_coverage(registry: dict[str, Source]) -> dict[int, list[str]]:
    """Which sources sit at each point on the axis.

    Used to answer "could this story even have been balanced?" -- a gap at
    lean=+2 means nothing if we aren't polling any right-leaning outlets.
    """
    buckets: dict[int, list[str]] = {lean: [] for lean in (-2, -1, 0, 1, 2)}
    for source in registry.values():
        if source.lean is not None and source.feeds:
            buckets[source.lean].append(source.id)
    return buckets
