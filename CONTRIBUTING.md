# Contributing to AlchemyLake for Databricks

Thanks for your interest. This repository — the Databricks App, the
`ai_render()` SQL function, and their docs — is Apache-2.0 licensed (see
[`LICENSE`](./LICENSE)) and open to contributions.

## What we welcome

- Issues and pull requests against the App (`app/`), the SQL function
  (`sql/`), the Asset Bundle (`databricks.yml`), and this documentation.
- Bug reports and reproductions, including against the MCP endpoint this
  bundle calls (`https://app.alchemylake.com/api/mcp`).

## Ground rules

1. Open an issue before a large change so we can align on direction.
2. Keep PRs focused and reviewable; include a clear description and test notes.
3. Never commit secrets. Configuration is via environment variables and
   Databricks secret scopes only.
4. For security issues, follow [`SECURITY.md`](./SECURITY.md) — do not open a
   public issue.

## Local development

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
databricks bundle validate -t prod
databricks bundle deploy  -t prod
databricks bundle run alchemylake_app -t prod
```

See the [README](./README.md) for the full walkthrough, including registering
this as an MCP server for Genie / Agent Bricks instead of deploying the App.

## Contributor License Agreement

We are finalizing a lightweight CLA for outside contributions. Until it is
published, by opening a PR you agree your contribution may be licensed under
this repository's Apache-2.0 terms. If your employer requires a signed
agreement, email **info@zorost.com** first.
