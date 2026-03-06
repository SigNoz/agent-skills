# SigNoz Agent Skills

Claude Code plugins that add SigNoz-specific skills to Claude.

## Plugins

- **clickhouse-query** — Write optimized ClickHouse queries for SigNoz OpenTelemetry data (traces)

## Install

```sh

/plugin marketplace add SigNoz/agent-skills
/plugin install clickhouse-query@signoz
```

After installing, the plugin's skills are available in any Claude Code session.

## Contributing

To test a plugin locally before publishing:

```sh
/plugin marketplace add ./agent-skills
/plugin install clickhouse-query@signoz
```
