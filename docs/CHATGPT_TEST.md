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
5. Run: `SMART بازار را اسکن کن و برای فولاد، پالایش و عیار تحلیل اولیه بده.`
6. Confirm that the tool call is `scan_market` and that the response contains
   source, price, volume ratio, RSI, MACD, MA/EMA history, smart-money phase,
   errors, decision-support ranking and the decision artifact id.
7. Run: `برای عیار آزمون walk-forward را با ۲۰ روز تاریخچه‌ی اولیه و پنجره‌های ۳۰ روزه اجرا کن.`
8. Confirm that the tool call is `walk_forward_exam`, the result reports
   `strategy_count=200`, segments and the leakage protocol, and that the
   response does not expose future labels as decision inputs.
9. If `OPENAI_API_KEY` is configured, run:
   `نتیجه‌ی آزمون عیار و دلایل ریسک را به فارسی توضیح بده.`
   This should call `chat_explain` and return an explanation based only on the
   supplied structured snapshot.

## Safety of the first test

The first live tool is read-only. It does not place orders, write to a broker, or claim guaranteed returns. TSETMC access can fail or be blocked depending on hosting IP; such failures must appear in the `errors` field rather than being replaced with invented data.

## Acceptance criteria

- `smart_health` returns configuration status without exposing the API key.
- `scan_smoke` returns deterministic data.
- `scan_market` reaches TSETMC and returns either live results or explicit source errors.
- `walk_forward_exam` runs chronologically with 20 initial bars and 30-bar evaluation segments.
- `list_strategies` reports exactly 200 auditable variants.
- `chat_explain` fails closed when `OPENAI_API_KEY` is absent and never exposes the key.
- Browser `/api/scan` returns the same live analysis pipeline.
- Browser `/api/exam` displays segment metrics and charts.
- Browser `/api/learning/<symbol>` exposes persisted wins, losses and failure reasons.
- ChatGPT can discover and call the SMART tools through the remote MCP server.

## Local Windows smoke test

From PowerShell in the repository root:

```powershell
$py = "C:\Users\PC101\anaconda3\python.exe"
$env:PYTHONPATH = ".\src"
& $py -m pytest -q
& $py -m uvicorn smart.webapp:app --reload
```

Then open `http://127.0.0.1:8000/`. The dashboard can run without an OpenAI key;
only the ChatGPT explanation button requires `OPENAI_API_KEY`.
