#!/usr/bin/env python3
"""Fetch a dashboard template JSON from the pinned SigNoz/dashboards commit.

Usage:
    python fetch_template.py <path>

where ``<path>`` is the template path within the upstream repo
(e.g. ``postgresql/postgresql.json``). Writes the raw response body tocan 
stdout. On HTTP or network failure, writes a short message to stderr
and exits non-zero.
"""

from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

PINNED_SHA = "61d374c50f9e1383e0eba3584fb81498f38c1f8d"
BASE_URL = "https://raw.githubusercontent.com/SigNoz/dashboards"

FETCH_TIMEOUT_SECONDS = 30


def build_url(path: str) -> str:
    path = path.lstrip("/")
    encoded = quote(path, safe="/")
    return f"{BASE_URL}/{PINNED_SHA}/{encoded}"


def fetch(path: str) -> bytes:
    url = build_url(path)
    with urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
        body: bytes = response.read()
        return body


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Template path, e.g. postgresql/postgresql.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        body = fetch(args.path)
    except HTTPError as exc:
        sys.stderr.write(f"HTTP {exc.code} fetching {args.path}: {exc.reason}\n")
        return 1
    except URLError as exc:
        sys.stderr.write(f"Network error fetching {args.path}: {exc.reason}\n")
        return 1

    sys.stdout.buffer.write(body)
    if not body.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
