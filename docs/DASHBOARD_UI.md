# Dashboard UI

The default `/` dashboard uses local CSS and JavaScript with no chart CDN dependency.
The layout separates decision, conditional entry/stop/targets, observed price and volume,
expandable evidence layers, and the ten model views. Number formatting is display-only;
the original report links and chart API preserve source precision. Decimal quantities
inside explanatory text are marked approximately when rounded. Versions and dates are preserved.

Chart controls: mouse wheel zoom around cursor, mouse drag to pan, zoom buttons,
session presets, keyboard `+` / `-`, arrow keys, and Home to reset to 90 sessions.
Mobile users have the same presets and zoom buttons; vertical page scrolling remains available.
The read-only chart endpoint projects immutable raw history after excluding invalid,
future, incomplete and missing-volume rows and respecting the report's last valid date.
No new analysis or backtest runs are required to display saved reports.

Focused validation:

- `python -m pytest tests/test_dashboard.py -q`: 2 passed.
- Existing default-route test: 1 passed, 8 deselected.
- `node tests/dashboard_behavior.cjs`: zoom, wheel, pan, keyboard, range bounds and formatting passed.
- Live root and both local assets returned HTTP 200.
- Saved Foolad chart returned 3,946 bars ending 2026-09-27, excluding the incomplete 2026-09-28 session.

Browser screenshot verification was unavailable in this session; layout and interactions
were checked through route responses and the actual JavaScript with a DOM/canvas harness.

Git message: `feat(ui): redesign Persian dashboard with integer display and zoomable price chart`
