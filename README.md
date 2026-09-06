# cn-hospital-aliases

An auditable, dependency-free Python library for resolving multiple Chinese
hospital names to a canonical hospital identity.

It is designed for clinical operations, vendor/site trackers, public-data
research, and record linkage where the same hospital may appear under a formal
name, a short name, a parallel institutional name, or a historical name.

> Status: alpha. Version 0.4 defaults to official NMPA/CFDI drug-trial
> institution filing identities and source-reviewed aliases. The goal is site
> name normalization, not trial-volume ranking. Unmatched names and ROR-only
> references never create official identities. The pinned filing snapshot is
> dated 2026-09-05; it is not a live eligibility check.

## Official identity policy

An input site name maps to the **literal official filing name**, filing number,
project ID and filing status. One filing record is one identity anchor. Preserve
parenthetical names and campus qualifiers in the canonical field. The project
ID is not a government-issued code; the filing number remains a separate field.

Only filing-listed names and explicitly source-reviewed aliases are used for
default exact resolution. ROR labels are review leads, not automatic approved
aliases. No match remains unmatched; a collision remains ambiguous. Separate
filings, branches, managed hospitals and campuses are not merged based on name
similarity. Historical name resolution does not establish present eligibility.

The original trial-volume queues remain available as optional prioritization
tools. They are not the library's scope or its completion criteria. A full NMPA
trial-detail export is **not required** to build or use the alias library.

Current outputs:

- `data/official/official_institutions.csv`: 2,039 literal filing identities.
- `data/official/approved_aliases.csv`: 2,674 name assertions, including 635
  noncanonical aliases across 328 filing identities.
- `data/official/alias_review_queue.csv`: 699 reference-only or split-component
  names requiring review.
- `data/official/trial_site_coverage.csv`: read-only linkage audit for the
  ClinicalTrials.gov China hospital-site snapshot.
- `data/official/trial_site_coverage_summary.json`: counts by exact match,
  location conflict and unmatched status.
- `data/official/trial_site_alias_review_queue.csv`: highest-volume unmatched
  site names and location conflicts for manual review; it does not approve
  aliases.
- `src/cn_hospital_aliases/data/official_site_aliases.jsonl.gz`: default library data.

### Chinese identity first; English may be deferred

`institution_confirmation_register.csv` checks every one of the 2,039 filing
identities against the pinned raw snapshot. Chinese filing names and filing
numbers are confirmed independently of English: 62 institutions have a reviewed
English name; 1,977 retain a blank English field with an explicit deferred status.
Unapproved candidate names and their sources remain in `pending_aliases_json`.
This is **not** confirmation of all reported trial-site names or live eligibility.

`data/curated/chinese_name_decisions.json` records the row-level review of all
359 Chinese candidate evidence records in this batch: 248 explicit hospital-level
co-listed names approved, 111 evidence records retained unapproved. Some retained
reference records duplicate independently approved filing evidence. No college,
institute, online hospital, network or ambiguous compound is approved merely by
splitting the filing text. Rebuild validates each approved decision against its
exact filing name and source URL; future candidates receive no automatic approval.
`data/curated/chinese_website_reviews.json` adds eleven separately sourced Chinese
aliases for eight institutions, including Suzhou, Shanghai Children's Medical Center,
Fuwai, Nantong, Hangzhou, Shuangliu, Ningbo and Wuhan. The 2026-09-06 reviews add
seven names, including historical names supported by a provincial rename approval
and hospital history. Approval dates are not assumed to be registration-effective dates; see
`docs/chinese-review-2026-09-06.md` for decisions and retained evidence gaps.
These partial reviews do not change literal filing names or certify all fields.
The remaining global queue has 79 Chinese and 620 non-Chinese evidence records.
The frozen trial-site queue still has 888 unresolved names, predominantly English;
deferring English does not authorize assigning these rows a guessed institution.

Rebuild without downloading or counting trial records:

```bash
PYTHONPATH=src python scripts/build_official_aliases.py
PYTHONPATH=src python scripts/check_official_aliases.py
PYTHONPATH=src python -m cn_hospital_aliases validate --summary-only
```

`HospitalRegistry.load_default()` and `load_official()` both use this official
view. Version 0.4 changes the former default six-record example dataset; that
dataset remains available through `load_seed()` and the CLI's `--seed` option.
`--master` / `load_master()` retain the v0.3 exploratory mixed-source view for
diagnostics only and are not the recommended normalization registry.

To map a research-center export:

```bash
PYTHONPATH=src python scripts/resolve_trial_sites.py sites.csv resolved.csv
```

Use `examples/trial_sites_template.csv` as the minimum intake schema. Keep the
source trial identifier and source URL so every resolved row remains auditable.

To profile the existing ClinicalTrials.gov site snapshot and produce a review
queue, run:

```bash
PYTHONPATH=src python scripts/audit_trial_site_coverage.py
```

For `matched_location_conflict`, confirmed identity fields stay empty.
`candidates_json` lists the name-only candidates with filing numbers and
locations for review; `candidate_count` includes those candidates. This status
means the location filter rejected the input, which may reflect spelling or
missing location aliases rather than an actual geographic conflict. Summed
group trial counts are not globally distinct trial totals.

Reviewed queue names are stored in `data/curated/trial_queue_reviews.json`.
After rebuilding the official registry, run
`PYTHONPATH=src python scripts/refresh_reviewed_sites.py` to refresh both the
hospital subset and all 38,784 cached facility groups. The first 1,000-row queue
is retained as `trial_site_review_baseline.csv`; `trial_site_review_progress.csv`
tracks name evidence against that fixed baseline. The cumulative queue-review
file has 51 institution records and 56 approved names, covering 106 baseline rows.
`trial_site_verification_register.csv` reconciles **every baseline row** with all
available approved evidence and preserves reference-only leads separately.
Its summary reports 112 rows with verified name relations, 199 reference-only
rows and 689 rows without approved name evidence. Of the 112 name-verified rows,
66 pass available location filters and 46 still require location review; those
46 rows have no confirmed institution ID. This is deterministic evidence
reconciliation, not a new manual review or completion of the 1,000-row review.
The baseline hash is recorded in `trial_site_verification_summary.json`.
Earlier name reviews include four Tianjin names supported by indexed
text of a university bilingual PDF whose direct retrieval failed. That access
limitation, branch exclusions and historical source dates are recorded in each
review's `review_scope`; they do not establish current trial eligibility.
An earlier six-name batch covers the first and second Zhejiang University hospitals,
the first China Medical University hospital and Shengjing Hospital. The last
uses an indexed bilingual header from the hospital's 2022 handbook; PDF text was
accessible but screenshot retrieval failed. A college-to-hospital translation
in a different paper was deliberately not used as an approved college alias.
The latest five names cover Qingdao University Affiliated Hospital, Henan
Provincial People's Hospital, Wenzhou Medical University's first hospital,
Hubei Cancer Hospital and Zhongnan Hospital. Only hospital-level names were
approved; laboratory, department and cooperating-hospital names remain separate.
All-site
outputs are `all_site_coverage.csv`, `all_site_review_queue.csv` and
`all_site_coverage_summary.json` under `data/official/`.

The input may use `facility_name`/`hospital_name` or `机构名称`/`医院名称`, with
optional province and city columns. Output rows contain the official Chinese
name, filing number/status, official project ID, matched alias and resolution
status. `--fuzzy` adds candidates only; it never fills an official ID.

## Why this project

The repositories inspected in the recorded GitHub search primarily provide
hospital lists, addresses, coordinates or medical-organization corpora. That
search did not identify a direct replacement for this filing-anchored workflow;
it is not a claim that no other alias library exists. See
[docs/github-research.zh-CN.md](docs/github-research.zh-CN.md).

## Features

- Exact canonical-name and alias resolution after conservative Unicode cleanup.
- Optional fuzzy candidate search using only the Python standard library.
- Province and city filters for disambiguation.
- Explicit alias kinds: `official_variant`, `common_short_name`,
  `parallel_name`, and `historical_name`.
- Source URL and effective-date fields for every alias.
- CSV batch resolution for operational trackers.
- Dataset validation, including collision warnings.
- A reproducible ClinicalTrials.gov China interventional-site snapshot.
- Zero runtime dependencies.

## Quick start

```bash
python -m pip install -e .

cn-hospital-alias resolve "哈医大三院" --json
cn-hospital-alias resolve "广慈医院"
cn-hospital-alias resolve "华西医科大学附属一院" --fuzzy
cn-hospital-alias stats
cn-hospital-alias validate
cn-hospital-alias --include-trial-sites stats
cn-hospital-alias --include-trial-sites resolve "Peking Union Medical College Hospital" --city Beijing
cn-hospital-alias --master resolve "West China Hospital, Sichuan University" --json
cn-hospital-alias --master stats
```

Python API:

```python
from cn_hospital_aliases import HospitalRegistry

registry = HospitalRegistry.load_default()
matches = registry.resolve("黑龙江省肿瘤医院")

for match in matches:
    print(match.hospital.canonical_name, match.match_type, match.score)
```

Batch CSV:

```bash
cn-hospital-alias batch examples/hospitals.csv resolved.csv \
  --column hospital_name \
  --province-column province \
  --city-column city
```

The output preserves all input columns and appends:

- `_resolution_status`
- `_hospital_id`
- `_canonical_name`
- `_matched_name`
- `_match_type`
- `_match_score`
- `_candidate_count`
- `_filing_number`
- `_filing_status`

## Data model

Each JSONL record has a stable project ID, canonical name, location, aliases,
and source metadata. Campuses are not treated as independent aliases by default.
See [docs/data-schema.md](docs/data-schema.md).

## Clinical-trial hospital snapshot

Refresh the full snapshot:

```bash
PYTHONPATH=src python scripts/sync_clinicaltrials_gov.py
```

The downloader uses the official ClinicalTrials.gov API v2, paginates all
matching records, caches each page atomically, and can resume an interrupted
run. Outputs are described in [data/README.md](data/README.md). Coverage and
quality limitations are documented in
[docs/source-coverage.zh-CN.md](docs/source-coverage.zh-CN.md).

Some macOS Python installations do not have a configured CA bundle. Point them
to the system bundle without disabling TLS verification:

```bash
SSL_CERT_FILE=/etc/ssl/cert.pem PYTHONPATH=src \
  python scripts/sync_clinicaltrials_gov.py
```

## Legacy exploratory master and optional prioritization

See [current coverage and review status](docs/master-data-status.zh-CN.md).

This section describes the retained v0.3 exploratory artifacts. Use
`data/official/` and the default registry for filing-anchored normalization.

- `data/master/hospital_master.sqlite`: institutions, names, identifiers,
  trial-site linkage evidence, and review priorities.
- `data/master/top1000_review.csv`: UTF-8 BOM CSV with source-specific counts,
  field completeness and review status. Blank NMPA counts mean unavailable.
- `data/master/top1000_candidates.csv`: candidate links requiring review.
- `data/master/top1000_audit_progress.csv`: website-check and field-review
  progress for every ranked record; a readable website is not an approval.
- `data/curated/official_reviews.json`: field-level official-source decisions.
- `data/curated/reference_decisions.json`: reviewed joins and quarantined records.
- `data/curated/website_identity_reviews.json`: explicitly reviewed website-to-
  filing crosswalks, with a narrower scope than complete identity review.

Rebuild from bundled cached reference data:

```bash
PYTHONPATH=src python scripts/build_master.py --accessed-at 2026-09-05
PYTHONPATH=src python scripts/check_master.py
PYTHONPATH=src python scripts/audit_official_sites.py --cached-only
```

Fetch a new CFDI public list snapshot (15 seconds between 100-row requests):

```bash
SSL_CERT_FILE=/etc/ssl/cert.pem PYTHONPATH=src python scripts/sync_cfdi.py \
  --output-dir data/raw/cfdi/new-snapshot
```

The public list establishes filing status only. The collector stops on an
access challenge or rate limit; it never requests captcha-protected details.
Cancelled filings are retained with an explicit status.

Import a legitimately obtained NMPA trial-to-institution export and rank that
export by distinct CTR identifiers per institution:

```bash
PYTHONPATH=src python scripts/build_master.py \
  --nmpa-csv /path/to/nmpa_participation.csv --rank-by nmpa
```

Column names are in `examples/nmpa_participation_template.csv`. Saved official
HTML details can first be converted with `scripts/import_nmpa_html.py` using a
JSON manifest of `path`, `source_url`, and `accessed_at` objects. These parsers
are fixture-tested; no live NMPA detail snapshot was available for production
schema validation. Partial imports are always labeled partial.

For a new ROR release, obtain the ZIP and metadata using the
[official ROR download instructions](https://ror.readme.io/docs/zenodo), then
pass `--ror-zip` and `--ror-metadata` to `build_master.py`. The ZIP checksum is
checked before use. Cached China healthcare references have their own SHA-256.

`HospitalRegistry.load_master()` is the corresponding Python API. Name-level
source evidence is available in SQLite; resolver JSON includes identifiers and
the identity verification status. ROR IDs, CFDI filing numbers and Chinese
Unified Social Credit Codes are separate identifier schemes.

```python
registry = HospitalRegistry.load_master()
hospital = registry.get_one(
    "The First Hospital of Jilin University", city="Changchun"
).hospital
same = registry.resolve_identifier("ror", "https://ror.org/034haf133")
```

Identifier lookup returns a tuple and preserves ambiguity. When a formerly
standalone ROR record joins a CFDI identity, its `cnha-ror-*` surrogate is kept
as a `legacy_master_id` identifier so existing references can be redirected.
English and Chinese location filters use explicit location aliases, not
machine translation.

To collect public website evidence for a later review batch, run
`scripts/audit_official_sites.py` without `--cached-only`. The collector caches
page titles/text, follows robots rules and stops on access failures. Website
ownership and identity still need adjudication. Existing cached results,
including failures, are reused rather than retried automatically.

## Safety and matching policy

This project deliberately avoids aggressive rules such as removing `省`, `市`,
`大学`, `附属`, or `医院`. Such rules improve recall but can merge different
institutions. Exact alias matches are preferred. Fuzzy results are candidates,
not authoritative identity decisions, and should be reviewed before modifying
clinical, regulatory, contracting, or payment records.

Exact matches are never truncated by `--limit`, because hiding a collision
could falsely imply uniqueness. The limit applies to fuzzy suggestions only.
Batch fuzzy results are marked `fuzzy_candidate` and do not populate approved
hospital IDs or canonical names. A zero CTG count means no linked trial in the
pinned CTG snapshot; an unavailable NMPA count remains null, never zero.

The bundled `hospital_id` values are project identifiers, not government-issued
organization codes. `verification_status=registry_reported` means the name was
reported in a trial record and matched a hospital-name pattern; it does not mean
the registry verified the identity. Names and affiliations can change. Always
inspect the source URL and `accessed_at` date for high-stakes use.

## Extend the dataset

Read [CONTRIBUTING.md](CONTRIBUTING.md), add a curated source-backed review and
rebuild the generated official dataset, then
run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/check_official_aliases.py
PYTHONPATH=src python -m cn_hospital_aliases validate
```

Prefer official hospital, health commission, university, or government sources.
Do not add an unsourced common abbreviation merely because it is plausible.

## License

Code is available under the MIT License. Dataset contribution and source-rights
notes are in [DATA_LICENSE.md](DATA_LICENSE.md).
