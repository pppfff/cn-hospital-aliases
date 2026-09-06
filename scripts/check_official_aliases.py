"""Reconcile default identities and alias evidence to the official filing cache."""
import csv
import json
from pathlib import Path

from cn_hospital_aliases import HospitalRegistry
from cn_hospital_aliases.normalizer import normalize_name
from cn_hospital_aliases.official import APPROVED_EVIDENCE
from cn_hospital_aliases.sources.cfdi import read_institutions
from cn_hospital_aliases.validation import validate_hospitals


def check():
    registry = HospitalRegistry.load_official()
    filings = {"cnha-cfdi-" + row["companyId"].lower(): row for row in read_institutions(Path("data/raw/cfdi/2026-09-05-batch100"))}
    assert {h.hospital_id for h in registry.hospitals} == set(filings)
    by_id = {}
    alias_evidence = {}
    for hospital in registry.hospitals:
        filing = filings[hospital.hospital_id]
        assert hospital.canonical_name == filing["compName"]
        assert hospital.filing_number == filing["recordNo"]
        assert hospital.source_url == filing["source_url"]
        assert hospital.verification_status == "official_filing"
        assert hospital.trial_count is None and hospital.nmpa_trial_count is None
        by_id[hospital.hospital_id] = {normalize_name(hospital.canonical_name), *(normalize_name(alias.name) for alias in hospital.aliases)}
        for alias in hospital.aliases:
            alias_evidence[(hospital.hospital_id, normalize_name(alias.name))] = alias
    with Path("data/official/approved_aliases.csv").open(encoding="utf-8-sig", newline="") as handle:
        names = list(csv.DictReader(handle))
    assert len(names) == sum(len(values) for values in by_id.values())
    assert len({(row["hospital_id"], row["normalized_alias"]) for row in names}) == len(names)
    for row in names:
        assert row["evidence_status"] in APPROVED_EVIDENCE and row["source_url"] and row["accessed_at"]
        assert row["normalized_alias"] in by_id[row["hospital_id"]]
        if row["kind"] != "canonical":
            alias = alias_evidence[(row["hospital_id"], row["normalized_alias"])]
            assert (alias.source_url, alias.accessed_at, alias.kind) == (row["source_url"], row["accessed_at"], row["kind"])
            assert (alias.valid_from or "", alias.valid_to or "") == (row["valid_from"], row["valid_to"])
    with Path("data/official/alias_review_queue.csv").open(encoding="utf-8-sig", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    approved_by_id = {(row["hospital_id"], row["normalized_alias"]) for row in names}
    assert all((row["hospital_id"], normalize_name(row["candidate_alias"])) not in approved_by_id for row in candidates)
    validation = validate_hospitals(registry.hospitals)
    assert validation.ok, validation.errors[:5]
    result = {"official_identity_count": len(filings), "literal_filing_names_verified": len(filings), "approved_name_assertions": len(names), "reference_only_candidates_excluded": len(candidates), "validation_errors": 0, "validation_warnings": len(validation.warnings), "ambiguous_names": len(registry.alias_collisions()), "trial_count_dependency": False}
    Path("data/official/validation_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
