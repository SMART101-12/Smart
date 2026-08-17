# SMART Daily AI Protocol

## Purpose
Keep the project continuously resumable and prevent loss of decisions between days, chats, or AI systems.

## Daily sequence
1. Read `AI_TRAINING/README.md`.
2. Read `AI_TRAINING/SMART_LOGIC.md`.
3. Read `docs/SMART_PROJECT_STATE_2026-08-17.md` or its newest replacement.
4. Read the newest experiment/comparison artifacts.
5. Inspect recent Git commits and runtime artifacts.
6. Check data-quality/calendar status before using new dates.
7. Identify one or more controlled experiments that are actually justified by the current evidence.
8. Run tests/experiments.
9. Record raw result artifacts in Git.
10. Update the project state and learning memory.
11. Mark each change as PROVEN, REJECTED, PENDING, MISSING, or PROMOTED.
12. Write a short daily handoff containing: what changed, evidence, failures, next action, and exact files/commits.

## Daily report minimum
- Date
- Data range used
- Symbols affected
- Data/calendar checks
- Experiment ID and engine version
- Baseline
- OOS size
- MAE
- Direction Accuracy
- Profit Factor / Expectancy / Drawdown when a trading strategy is tested
- Main error type
- Decision: Promote/Reject/Hold
- Reason
- Next experiment
- Git commit(s)

## Never do this
- Do not claim a result before the artifact exists.
- Do not use future data to create today's features.
- Do not tune on frozen OOS.
- Do not delete a weak result.
- Do not silently fetch an external price to replace Git data in a Git-defined experiment.
- Do not call a model superior because Direction Accuracy alone improved.
- Do not ask the user to re-answer a question already settled in Git documentation.

## Handoff style
The handoff must be understandable by a new AI with no chat history. Use exact file paths, experiment IDs, metrics, and decisions. Prefer facts over narrative.

## Automation boundary
The project can automate data collection and scheduled repository jobs through the user's local SMART agent/GitHub Actions where configured. ChatGPT itself cannot wake up autonomously every day or send an email without an enabled scheduling/email integration. Therefore the protocol is designed so that whenever the AI is invoked, it can continue immediately from Git without reconstructing the project from memory.
