# SigNoz Agent Skills

SigNoz skills to teach agents on writing optimised clickhouse queries for making dashboards using OpenTelementry data (traces, logs)

## Plugins

- **clickhouse-query** — Write optimized ClickHouse queries for SigNoz OpenTelemetry data (traces)

## Installation

For querying traces data - `npx skills add https://github.com/SigNoz/agent-skills --skill signoz-query-traces`

For querying logs data - `npx skills add https://github.com/SigNoz/agent-skills --skill signoz-query-logs`


## Install using Claude Marketplace

```sh

/plugin marketplace add SigNoz/agent-skills
/plugin install clickhouse-query@signoz
```

After installing, the plugin's skills are available in any Claude Code session.

## Example Usage

<img width="727" height="611" alt="image" src="https://github.com/user-attachments/assets/57768ec6-dbb4-420b-b479-271734e0856f" />

<img width="718" height="500" alt="image" src="https://github.com/user-attachments/assets/09b688f8-0d53-467b-978e-8883d600d5e5" />
