# Verified analysis and analyst evidence package

Engine: `SMART-ANALYSIS-2.9`. Legacy computed contract: `analysis-contract-v2`.

## Execution

1. Resolve the instrument and fetch repository-backed market history. Capture public HTTP response bodies before HTTP/JSON validation, including failed and rejected responses.
2. Audit dates, duplicates, OHLC containment, volume, freshness and completed sessions. Keep the original input and explicit exclusions. Calculate the reference technical contract from the verified history, independently of the second live snapshot.
3. Verify financial publication evidence and calculate technical structure, flow, historical evaluations and the existing structural entry engine. Quality blockers prevent entry plans; absence of observed target evidence never produces replacement targets.
4. Calculate dated summaries over 20, 60, 120 and 250 observed sessions. State insufficient coverage and unverified price adjustment/calendar continuity explicitly.
5. Produce one reference decision and a Persian narrative rendered from its computed facts. The optional OpenAI call can only select fact IDs and their order. Local rendering retains every warning and conclusion; free text, changed numerical fields and unknown IDs are rejected. Failure uses the local narrative. The model runs in the bounded worker pool with a 30 second HTTP timeout, without automatic retries.
6. Save immutable artifacts and SHA-256 hashes. The dashboard displays the narrative and offers a downloadable analyst package.

## Interfaces and compatibility

`POST /api/chat` accepts `analysis_id` to explain a saved report. Without it, the same unified job pipeline runs once. An already active job returns 409 with its ID. `structured=true` enables the optional model outline; `include_exam` remains accepted, but the reference job owns research evidence rather than calculating another independent exam. `structured_analysis` is the unified reference report. `structured_analysis_ai`, when present, contains that reference and the locally rendered explanation, rather than a second model-generated numerical report.

`final_assessment.confidence_0_100` is null with `confidence_status=NOT_CALIBRATED`. The descriptive data score lives under `data_quality.score_0_100`. Missing factor scores remain null. No calibration or predictive accuracy is claimed.

`GET /api/analysis/{symbol}/{analysis_id}/analysts` downloads `analysts.json` after verifying the artifact hash. It contains the exact reference report, received raw history, verified history, exclusion audit, raw public response bodies in base64 with URLs/timestamps/hashes, stored financial documents and binary assets, announcements, parsing/synchronization evidence and market snapshots. It does not send this package to another service. Cached JSON is explicitly distinguished from original HTTP bytes. Source material is marked untrusted input for downstream AI consumers.

An append-only `source_responses.jsonl` journal preserves received bodies even if a job fails before producing a manifest. Completed capture is frozen so a late cancelled worker cannot change a hashed artifact. Existing saved reports are preserved; the new package is available for new analyses. Previously unrecorded original HTTP bytes cannot be recovered from normalized cache rows. Stored historical revisions may have retrieval/publication dates after the report cutoff and must be independently filtered before reuse.

## Verification

Regression coverage includes numerical substitution in schema-valid model JSON, unknown/duplicate fact IDs, preserving caveats, fallback without model access, full-window history coverage, rejected HTTP body preservation, frozen capture, scoped binary evidence export, download integrity and the hash of the narrative's reference. Source acquisition and model behavior are exercised with controlled adapters; these tests do not establish real-world prediction accuracy or continuous provider availability.

Validation: 319 Python tests passed, one skipped; all three JavaScript behavior suites passed. A local production-adapter run for فزر, ID `91f9a15a5da14ebe9da453a17a29f4ef`, used 1,370 stored history rows through 2026-10-25 and captured 11 live/cached source responses. Its package downloaded successfully; all captured body hashes matched, its embedded reference matched the report, and `/api/chat` rendered exactly the saved narrative. Codal returned HTTP 429; missing verified five-year fundamentals and historical industry context remained explicit, producing `PARTIAL` / `NO_SETUP` with no invented entry targets. The package included the 429 response and stored Codal source assets. This demonstrates the failure-handling path, not prediction accuracy.
