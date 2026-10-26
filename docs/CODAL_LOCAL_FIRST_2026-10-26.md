# Codal local-first synchronization

Before financial synchronization, `codal_inventory` inspects the persisted
financial reports, their parser versions, monthly document identities, raw
asset counts and consecutive annual coverage. Each sync result records this
pre-sync inventory as `local_inventory`.

Current parsed document identities are reused even when synchronization state
is absent after a restart. Metadata discovery still checks for publications and
amendments. Downloading an unchanged document uses the saved raw URL asset;
only missing assets or explicitly changed announcements need a network download.

A fresh financial sync is reused only after successful discovery and a complete
consecutive annual window. Partial, failed and incomplete windows retry discovery
without clearing stored reports. Official HTTP cooldown and verification handling
remain in effect. Failed annual amendments retain their identity in
`pending_changed`, so saving discovery metadata cannot hide a failed revision.

Missing annual years are relative to the newest locally observed fiscal year.
They do not prove that no newer report has been published. Successful discovery
also does not prove every metric is populated; financial quality checks remain
separate. Company synchronization retains its existing discovery freshness rules.
