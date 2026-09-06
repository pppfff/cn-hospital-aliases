# Changelog

## 0.4.0 — Unreleased

- Default to 2,039 NMPA/CFDI drug-trial filing identities from the pinned
  2026-09-05 snapshot, preserving literal registered names and filing numbers.
- Include 2,674 approved name assertions (635 noncanonical aliases); keep
  699 reference-only candidates outside default exact matching.
- Preserve per-alias evidence access dates in the packaged dataset and API.
- Separate exact identity matches, location conflicts and fuzzy candidates.
- Retain legacy seed, trial-site and exploratory master loaders explicitly.
- Add reviewed Chinese historical/affiliated names and evidence registers.
- English can remain deferred; no complete NMPA trial-participation dataset or
  exhaustive alias coverage is claimed.

### Migration

`load_default()` now uses filing anchors instead of six seed hospitals. Use
`load_seed()` for old examples. Canonical strings and project IDs may differ.
`load_all()` / `--include-trial-sites` combine the legacy seed and reported
trial-site records, not the official default. Avoid those modes for confirmed
filing identity normalization. An optional `Alias.accessed_at` field is added;
older files without it remain readable and return `None`.
