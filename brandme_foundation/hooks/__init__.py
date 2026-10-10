"""Pub/Sub topic loader. Single source of truth is hooks/topics.yaml.

Ported from Lux (hooks/__init__.py). The loader is domain-free; only
topics.yaml carries Brand.Me's garment-lifecycle event names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_TOPICS_PATH = Path(__file__).parent / "topics.yaml"


def load_topics() -> list[dict[str, Any]]:
    data = yaml.safe_load(_TOPICS_PATH.read_text())
    topics: list[dict[str, Any]] = data["topics"]
    seen: set[str] = set()
    for t in topics:
        name = t["name"]
        if name in seen:
            raise ValueError(f"duplicate hook topic: {name}")
        seen.add(name)
    return topics


def topic_names() -> list[str]:
    return [t["name"] for t in load_topics()]
