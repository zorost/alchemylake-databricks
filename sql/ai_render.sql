-- =====================================================================
-- AlchemyLake ai_render() — call governed creative from SQL / Genie
-- =====================================================================
-- Registers a Unity Catalog Python UDF so analysts and Genie can produce
-- provenance-sealed narrative directly in a query:
--
--     SELECT ai_render(
--       'One-sentence executive read of this quarter''s ridership',
--       'ntd_demo.ntd.gold_ridership_national_monthly'
--     ) AS narrative;
--
-- The UDF calls the AlchemyLake MCP endpoint, which enforces the credit
-- ledger and returns the sealed text (source · row count · sha256).
--
-- ---------------------------------------------------------------------
-- PREREQUISITES
-- ---------------------------------------------------------------------
-- 1) A serverless SQL warehouse / serverless compute with EXTERNAL NETWORK
--    ACCESS enabled for the workspace (Admin → Security → Serverless egress),
--    allowing HTTPS to app.alchemylake.com. Classic sandboxed Python UDFs
--    have no network egress and will raise a connection error by design.
-- 2) Your AlchemyLake developer key (alk_…) stored as a Databricks secret:
--       databricks secrets create-scope alchemylake
--       databricks secrets put-secret alchemylake api_key   -- paste alk_...
-- 3) Replace <CATALOG>.<SCHEMA> below with a UC schema you can CREATE FUNCTION in.
--
-- If you cannot enable serverless egress, use the MCP registration path instead
-- (register https://app.alchemylake.com/api/mcp as an external MCP server for
-- Genie / Agent Bricks) — no SQL function required.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION <CATALOG>.<SCHEMA>.ai_render(
  prompt    STRING COMMENT 'What to write.',
  source_id STRING DEFAULT NULL COMMENT 'Governed source id to seal against, e.g. catalog.schema.table.'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'AlchemyLake governed render — returns provenance-sealed narrative for the given prompt/source.'
AS $$
    import json
    import urllib.request

    # The developer key is read from the secret scope at call time via the
    # Databricks secrets HTTP context. When running inside a serverless UDF the
    # cleanest injection is an environment variable set on the warehouse:
    #   SET ai_render.api_key = secret('alchemylake','api_key');  (see note below)
    import os
    api_key = os.environ.get("ALCHEMYLAKE_API_KEY", "")
    mcp_url = os.environ.get("ALCHEMYLAKE_MCP_URL", "https://app.alchemylake.com/api/mcp")

    if not api_key:
        return "[ai_render] Missing ALCHEMYLAKE_API_KEY on the compute environment."

    arguments = {"prompt": prompt}
    if source_id:
        arguments["source_id"] = source_id

    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "sql",
        "method": "tools/call",
        "params": {"name": "render_governed_chat", "arguments": arguments},
    }).encode("utf-8")

    req = urllib.request.Request(
        mcp_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=110) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — surface the reason to the analyst
        return "[ai_render] " + str(exc)

    if "error" in data:
        return "[ai_render] " + str(data["error"].get("message", data["error"]))
    content = data.get("result", {}).get("content", [])
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
$$;

-- Grant usage to your analysts / Genie service principal:
-- GRANT EXECUTE ON FUNCTION <CATALOG>.<SCHEMA>.ai_render TO `account users`;
