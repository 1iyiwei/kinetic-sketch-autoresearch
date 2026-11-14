"""Run artifacts store paths relative to their run folder, so a run can be moved,
shared or committed, and never exposes local absolute paths. In memory, paths
stay absolute; they are made relative only when written to JSON."""

from __future__ import annotations

from pathlib import Path


def relativize(obj, base: Path):
    """Recursively turn absolute path strings under `base` into paths relative to it."""
    prefix = str(Path(base).resolve()) + "/"
    if isinstance(obj, str):
        return obj[len(prefix):] if obj.startswith(prefix) else obj
    if isinstance(obj, dict):
        return {k: relativize(v, base) for k, v in obj.items()}
    if isinstance(obj, list):
        return [relativize(v, base) for v in obj]
    return obj


def resolve(p: str | Path, base: Path) -> Path:
    """A stored path: relative to the run folder (new runs) or absolute (older runs)."""
    p = Path(p)
    return p if p.is_absolute() else Path(base) / p
