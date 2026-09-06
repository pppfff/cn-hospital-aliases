# Release-readiness review — 2026-09-06

## Assessment: share with caveats as an alpha

The local technical checks support an initial GitHub alpha release, not a claim
that every clinical-trial center alias is verified. No repository was initialized
in the project, and nothing was committed, pushed, or published.

## Issues fixed

1. Per-alias evidence access dates were present in the approval CSV but absent
   from package/API aliases. Added an optional field and independent CSV/package
   reconciliation plus a regression test. Filing access dates remain distinct.
2. Contribution rules still allowed broader campus/entity merges. Aligned them
   with one filing ID per identity and curated-review-only generated data changes.
3. Added the official v0.4 schema and migration notes; narrowed the GitHub search
   claim; corrected the dataset-license version and added attribution links.
4. Added credential/local-artifact ignore patterns and read-only CI permissions.
   CI now also checks official evidence and smoke-tests the installed wheel.

## Checks performed

- 60 unit tests pass on the available local Python runtime. Intentional malformed
  CSV test output is expected; the suite finishes successfully.
- 2,039 literal filing identities reconcile to the checksum-verified raw cache.
- 2,674 approved assertions, 635 noncanonical aliases, 328 identities with aliases;
  no normalized cross-identity collisions and no validation errors.
- 699 pending evidence records: 79 Chinese and 620 non-Chinese. These are
  candidate evidence records, not distinct unconfirmed hospitals.
- Frozen 1,000-row baseline unchanged: 112 name relations supported, of which
  66 pass location filters and 46 remain location-review cases; 888 unresolved.
- Official quality notebook cells execute successfully; both notebooks have no
  saved output blocks. Local Markdown links checked with no missing targets.
- Wheel installs without dependencies in a temporary isolated environment and
  works outside the checkout. All four bundled datasets load. All official
  aliases retain access dates. Package dataset bytes match the working dataset;
  no raw caches, bytecode or local build garbage in the wheel.
- Git ignore behavior checked with a temporary Git metadata directory, without
  creating project Git history. Candidate content is about 87 MB; largest file
  is the approximately 41 MB legacy exploratory SQLite database. Its integrity
  check passes. Raw website/API page caches are excluded by the ignore rules.
- Heuristic secret/local-path scan of 128 relevant text/compressed files found
  no matching common token, private-key, credential-assignment or personal-path
  patterns. All 2,039 stored CFDI rows contain only the permitted institutional
  fields; no contact-person or telephone fields. This is not a complete privacy
  audit, and Git ignore rules do not protect a manual whole-folder upload.

## Remaining caveats and release gates

- 17 legacy HTTP evidence-source warnings remain intentionally visible. This
  review did not re-fetch every hospital source or certify its current ownership.
- No live filing eligibility refresh or complete NMPA/CDE trial-detail export.
  English remains deferred for 1,977 filing identities. Legacy mixed-source
  artifacts are not the default and are not independently re-adjudicated here.
- Local tests do not prove all advertised Python versions. The GitHub CI matrix
  for Python 3.10–3.13 must pass on the eventual repository before tagging.
- ROR's CC0 statement and the FCDO attribution were checked against their primary
  pages. The ClinicalTrials.gov terms page did not expose substantive text to the
  browsing tool. Source-specific redistribution terms, especially for optional
  extracts, are not comprehensively cleared by this technical review. Retain
  DATA_LICENSE.md and obtain owner review of the intended public data scope.
- Repository owner/name, visibility and publication remain user decisions. Do
  not upload the full local folder with ignored caches. Keep the alpha label.

## Reproduction

```bash
python -m pip install -e .
PYTHONPATH=src python scripts/build_official_aliases.py
PYTHONPATH=src python scripts/check_official_aliases.py
PYTHONPATH=src python scripts/refresh_reviewed_sites.py
python -m unittest discover -s tests -v
python -m cn_hospital_aliases validate --summary-only
python -m pip wheel . --no-deps --wheel-dir dist
```

Execute the code cells of `notebooks/official-alias-quality.ipynb` from the
repository root. Install the resulting wheel into a clean environment and run
its CLI outside the repository before release. The CI file encodes that smoke
test for future runs. This report is technical validation, not regulatory or
legal advice.
