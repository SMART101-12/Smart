# Stage 5: money flow and conflicts

`flow.observed_client_type` uses TSETMC ClientType individual buy/sell volume only if the response itself carries a current, valid session date. `flow.price_volume_proxy` separately computes the current volume versus the prior 5 and 20 sessions and describes price direction. If an undated ClientType response arrives, actual individual flow is `UNAVAILABLE`, even if the legacy smart-money proxy displays a phase. When observed client type contradicts price/volume direction the status is `CONFLICTING` with a named conflict. Neither category is an automatic buy authorization.

Missing or undated ClientType history prevents verified historical flow replay. The source-derived buy power requires valid positive buyer and seller counts. The layer carries the old proxy for backward compatibility and keeps its provenance distinct.
