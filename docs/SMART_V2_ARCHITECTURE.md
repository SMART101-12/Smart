# SMART V2 Architecture

## Goal

SMART V2 is a modular market-data and decision-support architecture. Each subsystem has a single responsibility and communicates through explicit data contracts so that failure in one subsystem does not cascade into unrelated subsystems.

## Pipeline

```text
TSETMC / Market Sources
        |
        v
+-------------------+
|    acquisition    |  Receive and store raw data only
+-------------------+
        |
        v
+-------------------+
|    validation     |  Test dates, prices, volume, identity, gaps, etc.
+-------------------+
        |
   +----+----+
   |         |
 FAIL      PASS
   |         |
   v         v
validation  validated_market
_reports
             |
             v
      +--------------+
      |  processing  |  Normalize / derive indicators / features
      +--------------+
             |
             v
         processed_market
             |
             v
          +------+ 
          |  AI  |  Scoring / prediction / learning / optimization
          +------+
             |
             v
          reporting / portfolio
```

## Module boundaries

### acquisition
- Owns external market-data access.
- Reuses the existing TSETMC acquisition code where possible.
- Stores source data without analytical modification.
- Must not depend on AI or processing modules.

### validation
- Reads raw data and market-calendar rules.
- Runs deterministic data-quality tests.
- Produces PASS/FAIL results and evidence.
- Never silently fixes raw data.

### processing
- Reads only validated data.
- Performs normalization, derived fields, indicators and model features.
- Must not call TSETMC directly.

### ai
- Reads processed features and historical outcomes.
- Owns scoring, prediction, learning, weight optimization and model artifacts.
- Must not fetch market data directly.

### portfolio
- Owns positions, exposure, risk and trade-state logic.
- Independent from acquisition implementation.

### reporting
- Produces human-readable and machine-readable reports from validated/processed/AI outputs.

## Runtime data layers

```text
runtime/
├── raw_market/
├── validated_market/
├── processed_market/
├── validation_reports/
├── ai/
└── reports/
```

The existing runtime/history and other legacy paths are not deleted in V2. They remain available as historical sources until each dataset is inventoried, validated and migrated.

## Symbol naming

Filesystem identifiers use ASCII/English names. Persian display names remain inside metadata.

Example:

```text
PALAYESH_67675656072510693
```

where `PALAYESH` is the system identifier and `67675656072510693` is the TSETMC instrument code.

## Independence rule

A subsystem may consume an upstream contract, but must not reach around it. For example, AI may consume processed data but may not call TSETMC; processing may consume validated data but may not call TSETMC.
