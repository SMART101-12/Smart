# SMART AI TRAINING

This directory is intentionally isolated from the production/model code. It is the teaching layer for any AI that must continue SMART without repeatedly asking the user to explain the project.

## Read order
1. `AI_TRAINING/SMART_LOGIC.md`
2. `AI_TRAINING/DAILY_AI_PROTOCOL.md`
3. `AI_TRAINING/GOLD_ETF_KNOWLEDGE.md` — persistent gold-ETF comparison, AYAR reasoning, relative-value logic, and candidate scoring framework
4. `docs/SMART_PROJECT_STATE_2026-08-17.md`
5. `docs/AI_HANDOFF.md`
6. `docs/SMART_MASTER_ROADMAP.md`
7. Latest experiment and comparison artifacts under `docs/` and `runtime/experiments/`

## Core idea
SMART is not a stock-picking chatbot. It is a controlled research loop:

`Observe -> Predict -> Record -> Reveal Actual -> Diagnose -> Learn -> Re-test`

The AI is the research manager. It proposes hypotheses, runs controlled experiments, records failures, and promotes only evidence-backed improvements.

## Status labels
- **PROVEN**: supported by reproducible tests and artifacts.
- **REJECTED**: tested and failed an acceptance gate.
- **PENDING**: specified but not sufficiently tested.
- **MISSING**: requires a new data layer or implementation.
- **PROMOTED**: passed the project's acceptance gates and is allowed into the active production path.

## Golden rules
- Never use future information.
- Never tune against frozen OOS.
- Never replace Git experiment data with an unrecorded external price source.
- Never delete failed experiments.
- Never call a model better without numeric baseline comparison.
- Never use Win Rate alone.
- Never fake unavailable order-book, flow, news, or sentiment history.
- Every important change needs a version, experiment record, result, and Git commit.

## Current teaching example
`daily-prediction-v1.0` is a **REJECTED** model. Its Palayesh walk-forward MAE was 1.8333% versus 1.8115% for Naive, so the extra complexity did not add predictive value. This failure is part of SMART's training memory and must not be erased.

## Persistent knowledge rule
`AI_TRAINING/` is the durable teaching memory. Important conclusions from future chats must be converted into dated, versioned documents here or into linked experiment artifacts. A future AI should be able to reconstruct the reasoning from Git even if model/session memory is unavailable.

## What the next AI should do
Start from the current Git state, not from assumptions. Identify what is proven/rejected/pending/missing, select one controlled next experiment, run it, record the result, and update the handoff/state documents.
