# SMART deployment

## Browser MVP
Deploy the repository with the included `render.yaml`. The `smart-market-intelligence` service exposes `/` and `/health`.

## MCP
The `smart-mcp` service runs the Streamable HTTP MCP server. Its public MCP endpoint is the service URL exposed by the host.

## Secrets
Set `OPENAI_API_KEY` in the hosting provider's secret/environment settings. Never commit the key to GitHub.

## Current limitation
The browser dashboard currently runs a safe smoke-test scan. Live market-source adapters must be enabled and validated before using live prices or trade decisions.
