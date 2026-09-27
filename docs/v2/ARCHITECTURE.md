# SMART V2 Architecture

SMART V2 is isolated from the legacy application on `smart-v2-data-validation`.

## Module boundaries

```text
TSETMC / other sources
        |
        v
  acquisition
        |
        v
  raw_market
        |
        v
   validation -----> validation_reports
        |
       PASS
        v
 validated_market
        |
        v
    processing
        |
        v
 processed_market
        |
        v
        AI
```

### Rules

1. `acquisition` owns source communication and raw capture only.
2. `validation` reads raw data and writes validation results; it never calls an AI model.
3. `validated_market` contains only data that passed the configured validation policy.
4. `processing` consumes validated data only; it does not fetch from TSETMC.
5. `AI` consumes processed/validated datasets through stable contracts; it does not own acquisition.
6. Reports and experiment results must reference immutable dataset/run identifiers.
7. Legacy branches and legacy runtime paths are not modified by V2 work.
8. V2 paths and code use English/ASCII names. Display names such as `پالایش` belong in metadata, not filesystem paths.

## First migration target

`PALAYESH_67675656072510693` is the first validation target. Existing historical data is evidence/input only; it is not considered verified until V2 validation runs succeed.
