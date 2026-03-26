"""
Auto-discover capability routers.

Each subdirectory under capabilities/ that has a router.py with a `router`
attribute gets registered automatically. To add a new capability:
  1. Create capabilities/my_thing/router.py
  2. Define `router = APIRouter(prefix="/api/v1/my-thing")`
  3. Restart — it's wired in.
"""

import importlib
import pkgutil
from pathlib import Path
from fastapi import APIRouter


def discover_routers() -> list[APIRouter]:
    """Walk capabilities/ subdirectories and collect APIRouter instances."""
    routers: list[APIRouter] = []
    package_dir = Path(__file__).parent

    for info in pkgutil.iter_modules([str(package_dir)]):
        if not info.ispkg:
            continue
        try:
            mod = importlib.import_module(f".{info.name}.router", package=__package__)
            if hasattr(mod, "router") and isinstance(mod.router, APIRouter):
                routers.append(mod.router)
        except (ImportError, AttributeError):
            pass  # Skip malformed capability packages

    return routers
