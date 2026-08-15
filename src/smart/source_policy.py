"""Source hierarchy and evidence rules for Iranian market data."""

PRIMARY_EXCHANGE = "tsetmc"

# A proxy is acceptable for discovery/cross-checking, but the report must keep
# the proxy name and never present it as the exchange itself.
PROXY_SOURCES = {
    "broker_feed",
    "market-data-provider",
    "financial-website",
}


def classify_source(source: str) -> str:
    source = source.lower().strip()
    if source == PRIMARY_EXCHANGE:
        return "primary_exchange"
    if source in PROXY_SOURCES:
        return "proxy_or_secondary"
    return "unclassified"


def evidence_policy(source: str) -> dict:
    kind = classify_source(source)
    return {
        "source": source,
        "kind": kind,
        "allowed_for_live": kind in {"primary_exchange", "proxy_or_secondary"},
        "must_show_source_in_report": True,
        "must_show_observation_date": True,
        "must_show_retrieval_time": True,
        "can_claim_current_day": kind == "primary_exchange",
    }
