#!/usr/bin/env python3
"""Build a clean Agent Plugins package from the SigNoz compatibility source."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "plugins" / "signoz"
SKILLS_ROOT = SOURCE_ROOT / "skills"
PORTABLE_ROOT_FILES = ("plugin.json", "mcp.json")


def ignore_nonportable_files(directory: str, names: list[str]) -> set[str]:
    """Exclude caches, eval workspaces, and immediate skill test data."""
    ignored = {
        name
        for name in names
        if name == "__pycache__" or name == ".DS_Store" or name.endswith(".pyc")
    }
    if Path(directory) == SKILLS_ROOT:
        ignored.update(name for name in names if name.endswith("-workspace"))
    elif Path(directory).parent == SKILLS_ROOT:
        ignored.update({"evals", "tests"}.intersection(names))
    return ignored


def normalize_skill_frontmatter(skill_md: Path) -> None:
    """Move Claude-only argument-hint into portable Agent Skills metadata."""
    lines = skill_md.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"missing YAML frontmatter: {skill_md}")

    try:
        frontmatter_end = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as error:
        raise ValueError(f"unterminated YAML frontmatter: {skill_md}") from error

    hint_indexes = [
        index
        for index, line in enumerate(lines[1:frontmatter_end], start=1)
        if line.startswith("argument-hint:")
    ]
    if not hint_indexes:
        return
    if len(hint_indexes) != 1:
        raise ValueError(f"multiple top-level argument-hint fields: {skill_md}")

    hint_index = hint_indexes[0]
    hint_value = lines[hint_index].split(":", 1)[1].strip()
    if not hint_value or hint_value.startswith((">", "|")):
        raise ValueError(
            f"argument-hint must use a non-empty single-line scalar: {skill_md}"
        )
    metadata_indexes = [
        index
        for index, line in enumerate(lines[1:frontmatter_end], start=1)
        if line.rstrip("\r\n") == "metadata:"
    ]

    if metadata_indexes:
        if len(metadata_indexes) != 1:
            raise ValueError(f"multiple top-level metadata fields: {skill_md}")
        metadata_index = metadata_indexes[0]
        metadata_end = metadata_index + 1
        while metadata_end < frontmatter_end and (
            not lines[metadata_end].strip() or lines[metadata_end].startswith((" ", "\t"))
        ):
            if lines[metadata_end].lstrip().startswith("argument-hint:"):
                raise ValueError(f"metadata.argument-hint already exists: {skill_md}")
            metadata_end += 1
        del lines[hint_index]
        if hint_index < metadata_end:
            metadata_end -= 1
        lines.insert(metadata_end, f"  argument-hint: {hint_value}\n")
    else:
        lines[hint_index : hint_index + 1] = [
            "metadata:\n",
            f"  argument-hint: {hint_value}\n",
        ]

    skill_md.write_text("".join(lines), encoding="utf-8")


def build(output: Path) -> Path:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")

    for filename in PORTABLE_ROOT_FILES:
        source = SOURCE_ROOT / filename
        if not source.is_file():
            raise FileNotFoundError(f"required portable source is missing: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(tempfile.mkdtemp(prefix=".signoz-agent-plugin-", dir=output.parent))
    temporary_package = temporary_parent / output.name
    try:
        temporary_package.mkdir()
        for filename in PORTABLE_ROOT_FILES:
            shutil.copy2(SOURCE_ROOT / filename, temporary_package / filename)
        shutil.copy2(REPO_ROOT / "LICENSE", temporary_package / "LICENSE")
        shutil.copytree(
            SKILLS_ROOT,
            temporary_package / "skills",
            ignore=ignore_nonportable_files,
        )

        for skill_md in sorted((temporary_package / "skills").glob("*/SKILL.md")):
            normalize_skill_frontmatter(skill_md)

        os.replace(temporary_package, output)
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=REPO_ROOT / "dist" / "signoz",
        help="new directory to create (default: dist/signoz)",
    )
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
