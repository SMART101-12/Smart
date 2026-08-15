# SMART — ChatGPT test setup

## Current architecture

- `src/smart/tsetmc.py`: live TSETMC adapter
- `src/smart/server.py`: read-only MCP tools
- `src/smart/mcp_http.py`: Streamable HTTP MCP entrypoint
- `src/smart/webapp.py`: browser dashboard
- `render.yaml`: two hosted services

## Required hosted services

Render (or another HTTPS host) must expose:

1. Dashboard: `https://<dashboard-host>/`
2. MCP: `https://<mcp-host>/mcp`

Set `OPENAI_API_KEY` as a secret environment variable on the hosted service. Never commit it.

## ChatGPT test

1. Deploy the repository and wait for both services to become healthy.
2. Open the ChatGPT Apps/MCP developer testing flow for your account.
3. Add the remote MCP server URL: `https://<mcp-host>/mcp`.
4. Enable the SMART tools.
5. Run: `SMART بازار را اسکن کن و برای شلرد، پالایش و عیار تحلیل اولیه بده.`
6. Confirm that the tool call is `scan_market` and that the response contains source, price, volume ratio, RSI, smart-money phase, errors, and ranking.

## Safety of the first test

The first live tool is read-only. It does not place orders, write to a broker, or claim guaranteed returns. TSETMC access can fail or be blocked depending on hosting IP; such failures must appear in the `errors` field rather than being replaced with invented data.

## Acceptance criteria

- `smart_health` returns configuration status without exposing the API key.
- `scan_smoke` returns deterministic data.
- `scan_market` reaches TSETMC and returns either live results or explicit source errors.
- Browser `/api/scan` returns the same live analysis pipeline.
- ChatGPT can discover and call `scan_market` through the remote MCP server.
