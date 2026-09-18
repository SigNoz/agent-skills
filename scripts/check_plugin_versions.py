#!/usr/bin/env python3
"""Check plugin manifest version parity and encode CalVer as strict SemVer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_MANIFESTS = (
    Path(".claude-plugin/plugin.json"),
    Path(".codex-plugin/plugin.json"),
    Path(".cursor-plugin/plugin.json"),
    Path(".grok-plugin/plugin.json"),
)


def encode_calver(calver: str) -> str:
    """Encode YYYY.MM.DD[.MICRO] as monotonic strict SemVer."""
    parts = calver.split(".")
    if len(parts) not in (3, 4) or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid CalVer: {calver}")

    year_text, month_text, day_text = parts[:3]
    micro_text = parts[3] if len(parts) == 4 else "0"
    year = int(year_text)
    month = int(month_text)
    day = int(day_text)
    micro = int(micro_text)

    if year < 1 or year_text != str(year):
        raise ValueError(f"invalid CalVer year: {calver}")
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ValueError(f"invalid CalVer date: {calver}")
    if not 0 <= micro <= 99:
        raise ValueError(
            f"CalVer micro suffix exceeds the supported 0-99 range: {calver}"
        )

    # Strict SemVer forbids leading zeroes in numeric identifiers. Folding the
    # micro suffix into patch precedence also avoids build metadata, which
    # SemVer deliberately ignores during comparisons.
    return f"{year}.{month}.{day * 100 + micro}"


def read_version(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"required plugin manifest is missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read plugin manifest {path}: {error}") from error

    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"no version field in {path}")
    return version


def check_versions(plugin_dir: Path) -> None:
    plugin_dir = plugin_dir.resolve()
    primary_path = plugin_dir / CLIENT_MANIFESTS[0]
    calver = read_version(primary_path)

    for relative_path in CLIENT_MANIFESTS[1:]:
        manifest = plugin_dir / relative_path
        version = read_version(manifest)
        if version != calver:
            raise ValueError(
                f"version mismatch: {manifest} has {version}, expected {calver}"
            )

    expected_semver = encode_calver(calver)
    portable_manifest = plugin_dir / "plugin.json"
    portable_version = read_version(portable_manifest)
    if portable_version != expected_semver:
        raise ValueError(
            f"version mismatch: {portable_manifest} has {portable_version}, "
            f"expected {expected_semver}"
        )

    if plugin_dir.name == "signoz":
        compatibility_versions = (
            (REPO_ROOT / "gemini-extension.json", calver),
            (REPO_ROOT / ".devin-plugin/plugin.json", expected_semver),
        )
        for manifest, expected in compatibility_versions:
            version = read_version(manifest)
            if version != expected:
                raise ValueError(
                    f"version mismatch: {manifest} has {version}, expected {expected}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="encode a CalVer value")
    encode_parser.add_argument("calver")

    check_parser = subparsers.add_parser("check", help="check manifest parity")
    check_parser.add_argument("plugin_dir", type=Path)

    args = parser.parse_args()
    try:
        if args.command == "encode":
            print(encode_calver(args.calver))
        else:
            check_versions(args.plugin_dir)
            print(f"Plugin versions are consistent: {args.plugin_dir}")
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
