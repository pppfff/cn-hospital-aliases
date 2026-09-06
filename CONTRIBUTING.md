# Contributing hospital names

## Acceptance rules

1. Prefer a current official hospital, health commission, university, or
   government source.
2. Use one CFDI filing company ID per official identity. Preserve the literal
   filing name and filing number; do not invent identities from reported names.
3. Never merge separate filings, campuses or managed hospitals on name similarity
   or affiliation alone. A split label in a filing requires explicit review.
4. Classify every alternate name and provide its own source URL.
5. Use `historical_name` for documented former names. Populate validity dates
   only to the precision supported; approval dates need not be effective dates.
6. Do not infer an alias only by shortening words. Unsourced abbreviations are
   not accepted as verified data.
7. If one alias legitimately refers to multiple hospitals, keep both mappings;
   the validator will report a warning and the resolver will return candidates.

## Alias kinds

- `official_variant`: another current formal rendering of the hospital name.
- `common_short_name`: a short name explicitly used by an authoritative source.
- `parallel_name`: a source-confirmed second hospital name for the same filing anchor.
- `historical_name`: a documented former name; predecessor mergers need separate review.
- `english_name`: an English rendering from an authoritative source.

## Checklist

```bash
python -m pip install -e .
PYTHONPATH=src python scripts/build_official_aliases.py
PYTHONPATH=src python scripts/check_official_aliases.py
python -m unittest discover -s tests -v
PYTHONPATH=src python -m cn_hospital_aliases validate
```

Review every new collision warning. A collision may be valid, but it must not be
silently converted into a single match.

Add reviewed aliases to the appropriate `data/curated/*reviews.json` file, with
the exact existing `hospital_id`, per-name `source_url`, `accessed_at`, `kind`,
and a review scope. Do not edit generated package JSONL or CSV outputs by hand.
Leave `official_review_completed` false for partial name reviews. Preserve the
frozen trial-site baseline. Do not include downloaded webpages, credentials,
patient information or contact-person records in a contribution.
