# Dataset rights and provenance

The bundled dataset is a compilation of factual hospital-name mappings and
source URLs. Contributors license their original selection and arrangement
under Creative Commons Attribution 4.0 International (CC BY 4.0), to the extent
that such rights exist.

Names, trademarks, government identifiers, and material on linked source pages
remain subject to the rights and terms of their respective owners. A source URL
is evidence, not a grant to republish the source page. This repository does not
redistribute biographies, descriptions, logos, or other substantial source
content in its installable package or fact exports. The optional local crawler
cache in `data/raw/official_sites/` is ignored by Git and is not part of the
package. It must not be included in a public dataset release without a separate
source-rights review.

Downstream users are responsible for checking source currency and applicable
terms before high-stakes or commercial use.

The ROR reference subset is redistributed under CC0-1.0, as specified by
https://ror.readme.io/docs/data-dump. Its pinned release is identified in
`data/raw/ror/manifest.json`. ROR curation is reference evidence, not a Chinese
government legal-identity certification. Known conflicting records are excluded
through `data/curated/reference_decisions.json` while the original subset stays
unchanged for auditability.

CFDI public filing rows retain institution names, addresses, filing identifiers
and status only. Contact people and phone numbers returned by the public list
are excluded from the stored snapshot and deliverables. Filing metadata is not
trial-participation evidence. No NMPA/CDE trial detail database is bundled in
version 0.4.

Selected bilingual name assertions cite the FCDO's [List of medical facilities
in China](https://www.gov.uk/government/publications/list-of-hospitals-in-china/list-of-medical-facilities-in-china), updated 28 May 2025, Crown copyright 2025, licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). Only selected factual names and source links are
included. This source does not endorse hospitals or establish Chinese filing
status; each approved relation is anchored to the CFDI snapshot separately.

ClinicalTrials.gov-derived files are labeled separately from official filing
identities. See the [ClinicalTrials.gov terms](https://clinicaltrials.gov/about-site/terms-conditions)
before redistributing or using those optional extracts. These source notes do
not relicense third-party content or constitute a comprehensive legal clearance.
