#!/usr/bin/env python3
"""Search the bundled dashboard template catalog.

Usage:
    python search_templates.py "<query>" [--limit N] [--category NAME]
                               [--list-categories] [--catalog PATH]

Emits a JSON array to stdout. Each entry has: id, title, path,
description, category, score. Returns an empty array (exit 0) on
no match.

Pass ``--category`` to restrict results to a single category (case-
insensitive, matched against the catalog's ``category`` field). Pass
``--list-categories`` to print the sorted list of available categories
as a JSON array and exit; ``query`` may be empty when listing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "templates.json"

WEIGHT_KEYWORD_EXACT = 10
WEIGHT_TITLE_SUBSTRING = 5
WEIGHT_DESCRIPTION_SUBSTRING = 2

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _NON_ALNUM_RE.sub(" ", text.lower()).split() if t]


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


def _load_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    with catalog_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_categories(catalog_path: Path) -> list[str]:
    catalog = _load_catalog(catalog_path)
    seen: set[str] = set()
    for entry in catalog:
        category = entry.get("category")
        if category:
            seen.add(category)
    return sorted(seen)


def search(
    query: str,
    catalog_path: Path,
    limit: int,
    category: str | None = None,
) -> list[dict[str, Any]]:
    catalog = _load_catalog(catalog_path)

    if category:
        category_lower = category.lower()
        catalog = [
            e for e in catalog if (e.get("category") or "").lower() == category_lower
        ]

    query_tokens = _tokenize(query)

    scored: list[tuple[int, dict[str, Any]]] = []
    if query_tokens:
        for entry in catalog:
            score = _score_entry(entry, query_tokens)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].get("title", "")))
    elif category:
        # No query but a category filter: return everything in the category,
        # ordered by title. Score is 0 because nothing was actually scored.
        scored = [(0, entry) for entry in catalog]
        scored.sort(key=lambda pair: pair[1].get("title", "").lower())
    else:
        return []

    results: list[dict[str, Any]] = []
    for score, entry in scored[:limit]:
        results.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "path": entry.get("path"),
                "description": entry.get("description"),
                "category": entry.get("category"),
                "score": score,
            }
        )
    return results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query string (optional when --category is set)",
    )
    parser.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    parser.add_argument(
        "--category",
        default=None,
        help="Restrict results to a single category (case-insensitive)",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="Print the sorted list of available categories and exit",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Path to templates.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.list_categories:
        json.dump(list_categories(args.catalog), sys.stdout)
        sys.stdout.write("\n")
        return 0
    results = search(args.query, args.catalog, args.limit, category=args.category)
    json.dump(results, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())