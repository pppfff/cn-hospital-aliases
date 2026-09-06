# Data schema

The packaged dataset is UTF-8 JSON Lines. Each non-empty, non-comment line is
one hospital record.

```json
{
  "hospital_id": "cnha-230103-hmucancer",
  "canonical_name": "哈尔滨医科大学附属肿瘤医院",
  "province": "黑龙江省",
  "city": "哈尔滨市",
  "district": "南岗区",
  "source_url": "https://example.org/official-hospital-page",
  "accessed_at": "2026-09-04",
  "aliases": [
    {
      "name": "黑龙江省肿瘤医院",
      "kind": "official_variant",
      "source_url": "https://example.org/official-hospital-page",
      "valid_from": null,
      "valid_to": null,
      "note": "Listed in parentheses by the hospital."
    }
  ]
}
```

## Version 0.4 official default

The example above illustrates the legacy seed schema, not a filing identity.
`load_default()` / `load_official()` read `official_site_aliases.jsonl.gz`:

- `hospital_id`: `cnha-cfdi-<lowercase companyId>`, a project ID, not an official code.
- `canonical_name` and `official_name_zh`: the entire literal CFDI filing name.
- `filing_number`: the distinct drug-trial filing number.
- `filing_status`: status in the pinned filing snapshot, not live eligibility.
- `verification_status`: `official_filing`; no trial participation is implied.
- `english_name`: reviewed English name or an empty string when deferred.
- `official_review_completed`: full-field review flag, not exhaustive alias coverage.
- `aliases[].accessed_at`: the alias evidence access date. The hospital-level
  date belongs to the filing snapshot and may differ. Legacy data may omit the
  alias date; the API returns `null` in that case.

Approved name assertions with source, date, evidence status and historical
validity are also available in `data/official/approved_aliases.csv`. Unapproved
candidates remain outside the default resolver. Historical validity is metadata;
the resolver does not filter names by an as-of date.

## Required fields

- `hospital_id`: stable project-level identifier beginning with `cnha-`.
- `canonical_name`: literal filing name in the official default, or the
  dataset-specific display name in legacy data.
- `province`, `city`: location context for identity resolution.
- `source_url`: evidence for the canonical name.
- `accessed_at`: ISO date when the evidence was checked.
- `aliases`: list of zero or more alias objects.

Generated trial-site records additionally use:

- `verification_status`: `registry_reported`, distinct from `verified`.
- `source_registry`: currently `ClinicalTrials.gov`.
- `trial_count`: number of distinct trial records in the exact normalized
  name-and-location group.

The generated record's `canonical_name` is only its most frequent reported
presentation. It is not asserted to be the hospital's official Chinese name.

`district` is optional. Alias dates are ISO dates or years where known, and
otherwise `null`. Unknown does not mean current.

## Version 0.3 master data

`HospitalRegistry.load_master()` reads `hospital_master.jsonl.gz`. It adds:

- `identifiers`: objects with `scheme`, `value`, and `source_url`.
- `official_name_zh`: the first explicitly listed name in the CFDI filing.
- `english_name`: a reference or officially reviewed English rendering.
- `nmpa_trial_count`: null when participation records are unavailable.
- `city_aliases`, `province_aliases`: explicit bilingual location keys for filtering.
- `official_review_completed`: the requested identity field categories have
  official-source support; it does not certify exhaustive aliases or trial counts.

Master record status values include `official_filing`, `reference_curated`,
and `registry_reported`. Each name has its own evidence status in the SQLite
`names` table. A filing-backed record can still contain reference-only English
aliases. `reference_alias` does not assert that a name is historical.

SQLite tables:

| Table | Grain |
| --- | --- |
| institutions | One reference identity or explicitly unresolved name/location group |
| names | One name assertion with kind, source and date |
| identifiers | One identifier scheme/value per institution |
| trial_site_links | One reported trial-site row and linkage decision |
| review_priority | One provisional ranked review record |

Counts use distinct trial IDs within each source. NCT and CTR counts are never
summed without a validated cross-registry trial crosswalk. `cfdi_company_id`
and `cfdi_drug_filing` are official system/filing identifiers, not USCCs.
`legacy_master_id` preserves a formerly standalone `cnha-ror-*` project ID
after a reviewed or exact-reference join to a CFDI-backed identity. These can
be resolved with `resolve_identifier`; they are not additional legal entities.
