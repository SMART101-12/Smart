# SMART

Excel-first, modular, adaptive decision-support system for the Iran capital market.

## Current stage
**Sprint 1 — Live Scanner MVP / ChatGPT App preparation**

Workflow:
1. Live data collection
2. Multi-source validation
3. Pre-filter
4. Daily Top 10
5. Operator selects 2–3
6. Analysis modules
7. Risk / trade plan
8. Outcome logging
9. Learning & optimization

## What is live in the codebase now

- TSETMC live adapter for symbol search, instrument info, quote, daily history and حقیقی/حقوقی flow
- Technical primitives: SMA, EMA, RSI and volatility
- Multi-confirmation Smart Money phase engine
- Explainable ranking/scanner
- Read-only MCP tools
- Streamable HTTP MCP entrypoint
- Browser dashboard for first live analysis
- Docker + Render blueprint
- GitHub Actions test workflow

## ChatGPT App path

The MCP server is designed to be hosted at `https://<host>/mcp`. After HTTPS deployment, connect that remote MCP server in the ChatGPT Apps/MCP developer testing flow and call `scan_market`.

See [`docs/CHATGPT_TEST.md`](docs/CHATGPT_TEST.md) for the exact acceptance test.

## Data-source note

TSETMC endpoints used by the adapter are community-documented and can change or restrict access. SMART reports source failures explicitly and never fabricates missing market values. A second independent source will be added before production-grade multi-source validation.

## Security

The OpenAI API key is read only from `OPENAI_API_KEY`. It is never stored in source code or committed to GitHub.
