# PALAYESH V2 validated dataset

No daily record is stored here until it passes the V2 validation pipeline.

Expected layout:

```text
PALAYESH_67675656072510693/
  metadata.json
  2020/08/YYYYMMDD.json
  2020/09/YYYYMMDD.json
  ...
```

The source history remains immutable in its existing raw/history layer. Validation reports belong under `runtime/validation_reports/PALAYESH_67675656072510693/`.
