# Generated clinical-trial site data

Version 0.4 uses `official/` as the authoritative site-alias view. Its institution
table contains only official filing identities; `approved_aliases.csv` contains
source-backed names and `alias_review_queue.csv` contains unapproved reference
leads. Rebuild with `scripts/build_official_aliases.py`, then run
`scripts/check_official_aliases.py`. Older `master/` files are exploratory and
include non-authoritative groups; they are not the default resolver dataset.

Version 0.3 also includes `master/`, `curated/`, `raw/cfdi/`, `raw/ror/`, and
`raw/nmpa/access-status.json`. See `../docs/master-data-status.zh-CN.md` for
current progress. CFDI files represent institution filings, not trial sites.
The NMPA folder currently contains an access-status record only, not trial data.

Snapshot source: official ClinicalTrials.gov API v2.

Query scope:

- `AREA[LocationCountry]China`
- `AREA[StudyType]INTERVENTIONAL`

## Outputs

- `processed/facility_mentions.csv.gz`: one reported China facility occurrence
  per trial and location.
- `processed/facility_sites.csv.gz`: exact conservative normalized
  name/province/city groups for all named facilities.
- `processed/hospital_sites.csv.gz`: groups whose name contains a hospital or
  medical-center marker.
- `processed/verified_site_matches.csv.gz`: exact name-and-location matches to
  the manually verified seed.
- `processed/snapshot_stats.json`: coverage and data-quality counters.
- `review/alias_candidates.csv.gz`: same-city, same-script, high-similarity
  hospital-name pairs. Every row requires manual review.
- `src/cn_hospital_aliases/data/clinical_trial_hospitals.jsonl.gz`: packaged
  resolver records with `verification_status=registry_reported`.

Raw API pages are cached under `raw/clinicaltrials_gov/` for reproducibility and
resume support, but page files are ignored by Git because they are regenerable.
The source manifest is retained.

## Important interpretation

A row is a distinct reported `facility name + province + city` group, not a
proven unique legal hospital. One hospital may therefore have multiple rows due
to English translations, typos, missing province values, department prefixes,
or changed names. Conversely, generic names can refer to several hospitals.
