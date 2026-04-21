#!/usr/bin/env python3
"""Search the bundled dashboard template catalog.

Usage:
    python search_templates.py "<query>" [--limit N] [--catalog PATH]

Emits a JSON array to stdout. Each entry has: id, title, path,
description, score. Returns an empty array (exit 0) on no match.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "templates.json"

WEIGHT_KEYWORD_EXACT = 10
WEIGHT_TITLE_SUBSTRING = 5
WEIGHT_DESCRIPTION_SUBSTRING = 2


def _tokenize(text: str) -> list[str]:
    return [t for t in text.lower().replace("-", " ").replace("_", " ").split() if t]


def _score_entry(entry: dict[str, Any], query_tokens: list[str]) -> int:
    score = 0
    keywords = {k.lower() for k in entry.get("keywords", [])}
    title_lower = entry.get("title", "").lower()
    description_lower = entry.get("description", "").lower()

    for token in query_tokens:
        if token in keywords:
            score += WEIGHT_KEYWORD_EXACT
        if token in title_lower:
            score += WEIGHT_TITLE_SUBSTRING
        if token in description_lower:
            score += WEIGHT_DESCRIPTION_SUBSTRING
    return score


def search(
    query: str,
    catalog_path: Path,
    limit: int,
) -> list[dict[str, Any]]:
    with catalog_path.open("r", encoding="utf-8") as f:
        catalog = json.load(f)

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in catalog:
        score = _score_entry(entry, query_tokens)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("title", "")))

    results: list[dict[str, Any]] = []
    for score, entry in scored[:limit]:
        results.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "path": entry.get("path"),
                "description": entry.get("description"),
                "score": score,
            }
        )
    return results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Search query string")
    parser.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Path to templates.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    results = search(args.query, args.catalog, args.limit)
    json.dump(results, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
