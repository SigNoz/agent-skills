#!/usr/bin/env python3
"""Check client MCP manifest paths and server identities for a plugin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CLIENT_MCP_CONTRACTS = (
    (
        "Claude Code",
        Path(".claude-plugin/plugin.json"),
        Path(".signoz_claude_mcp.json"),
        {
            "mcp": {
                "type": "http",
                "url": "${user_config.SIGNOZ_MCP_URL}",
            }
        },
    ),
    (
        "Codex",
        Path(".codex-plugin/plugin.json"),
        Path("mcp.json"),
        {
            "signoz": {
                "type": "streamable-http",
                "url": "https://not-setup/mcp",
            }
        },
    ),
)


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"required JSON file is missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON file {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return data


def check_server_map(
    path: Path, expected_servers: dict[str, dict[str, str]]
) -> None:
    data = read_json(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError(f"expected an mcpServers object in {path}")

    if servers != expected_servers:
        raise ValueError(
            f"unexpected MCP server config in {path}: {servers!r}, "
            f"expected {expected_servers!r}"
        )


def check_client_mcp_configs(plugin_dir: Path) -> None:
    plugin_dir = plugin_dir.resolve()

    reserved_default = plugin_dir / ".mcp.json"
    if reserved_default.exists() or reserved_default.is_symlink():
        raise ValueError(
            f"reserved root MCP config must be absent to prevent duplicate discovery: "
            f"{reserved_default}"
        )

    for client_name, manifest_path, expected_target, expected_servers in (
        CLIENT_MCP_CONTRACTS
    ):
        manifest = plugin_dir / manifest_path
        manifest_data = read_json(manifest)
        declared_target = manifest_data.get("mcpServers")
        expected_declaration = f"./{expected_target.as_posix()}"
        if declared_target != expected_declaration:
            raise ValueError(
                f"{client_name} manifest {manifest} declares mcpServers="
                f"{declared_target!r}, expected {expected_declaration!r}"
            )

        resolved_target = (plugin_dir / expected_target).resolve()
        try:
            resolved_target.relative_to(plugin_dir)
        except ValueError as error:
            raise ValueError(
                f"{client_name} MCP config resolves outside the plugin root: "
                f"{resolved_target}"
            ) from error
        check_server_map(resolved_target, expected_servers)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin_dir", type=Path)
    args = parser.parse_args()

    try:
        check_client_mcp_configs(args.plugin_dir)
        print(f"Client MCP configs are consistent: {args.plugin_dir}")
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
