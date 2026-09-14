"""One tree-sitter walk of a repository, and the two documents derived from it: census and surface."""

from __future__ import annotations

from pathlib import Path

from fingerprint.census import census, render as render_census
from fingerprint.surface import surface, render as render_surface
from fingerprint.walk import Walk, walk

__all__ = ["Walk", "walk", "read", "census", "surface", "census_of", "surface_of",
           "render_census", "render_surface"]


def read(path: str | Path, name: str | None = None,
         exclude: tuple[str, ...] = ()) -> Walk:
    """Walk a repository once. Pass the result to `census` and `surface` as needed."""
    return walk(Path(path), name, exclude)


def census_of(path: str | Path, name: str | None = None,
              exclude: tuple[str, ...] = ()) -> dict:
    """The fingerprint document for a repository."""
    return census(read(path, name, exclude))


def surface_of(path: str | Path, name: str | None = None,
               exclude: tuple[str, ...] = (), packages: tuple[str, ...] = (),
               include_methods: bool = False) -> dict:
    """The mutation surface document for a repository, optionally scoped to named packages."""
    return surface(read(path, name, exclude), packages, include_methods)
