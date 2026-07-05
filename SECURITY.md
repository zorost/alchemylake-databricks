# Security Policy

This repository is the Databricks integration layer for AlchemyLake, a product of
Zorost Intelligence. We take the integrity of the platform — and of the governed
data our customers bind to it — seriously.

## Reporting a vulnerability

Please report suspected security issues privately to **info@zorost.com** with:

- a description of the issue and its impact,
- steps to reproduce (proof-of-concept if possible),
- affected component (the App, the `ai_render()` SQL function, or the MCP
  endpoint it calls).

Do **not** open a public issue for security reports. We aim to acknowledge
within 3 business days and to provide a remediation timeline after triage.

## Scope

In scope: everything in this repository (the App, the SQL function) and the
`/api/mcp` and `/api/public/v1` endpoints it talks to. Out of scope: third-party
infrastructure we depend on (Databricks itself) — report those to the
respective vendors.

## Handling of secrets and data

- No secrets are committed to this repository; configuration is via environment
  variables and Databricks secret scopes only.
- Developer keys (`alk_…`) are hashed at rest, shown once, and revocable.
- Only the rows you explicitly bind for a given render are sent to produce it;
  your other tables never leave the workspace, and bound data is not used for
  model training.

## Coordinated disclosure

We support coordinated disclosure and will credit reporters who wish to be named
once a fix is released.
