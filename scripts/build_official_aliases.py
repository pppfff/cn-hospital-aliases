"""Build filing-anchored aliases without trial-detail downloads or trial ranking."""
import hashlib
import json
from pathlib import Path

from cn_hospital_aliases.master import expand_website_reviews
from cn_hospital_aliases.official import official_records, write_official
from cn_hospital_aliases.sources.cfdi import read_institutions
from cn_hospital_aliases.review import chinese_name_reviews, institution_confirmation_register
from cn_hospital_aliases import Hospital, HospitalRegistry


def main():
    filings = read_institutions(Path("data/raw/cfdi/2026-09-05-batch100"))
    ror_path = Path("data/raw/ror/china_healthcare.json")
    manifest = json.loads(Path("data/raw/ror/manifest.json").read_text())
    if hashlib.sha256(ror_path.read_bytes()).hexdigest() != manifest["subset_sha256"]:
        raise ValueError("ROR auxiliary snapshot checksum mismatch")
    ror = json.loads(ror_path.read_text())
    reviews = json.loads(Path("data/curated/official_reviews.json").read_text())
    reviews += json.loads(Path("data/curated/trial_queue_reviews.json").read_text())
    # Apply partial name decisions before existing full-field reviews so they
    # cannot downgrade a previously completed institution review.
    supplemental_reviews = json.loads(Path("data/curated/chinese_website_reviews.json").read_text())
    reviews = chinese_name_reviews(json.loads(Path("data/curated/chinese_name_decisions.json").read_text()), filings) + supplemental_reviews + reviews
    decisions = json.loads(Path("data/curated/reference_decisions.json").read_text())
    links, website_reviews = expand_website_reviews(json.loads(Path("data/curated/website_identity_reviews.json").read_text()))
    decisions.setdefault("ror_to_cfdi", []).extend(links)
    records, assertions, candidates = official_records(filings, ror, reviews=website_reviews + reviews, decisions=decisions, accessed_at="2026-09-05")
    summary = write_official(records, assertions, candidates, directory=Path("data/official"), package_output=Path("src/cn_hospital_aliases/data/official_site_aliases.jsonl.gz"))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(institution_confirmation_register(Path("data/official"), HospitalRegistry(Hospital.from_dict(row) for row in records), filings), indent=2))


if __name__ == "__main__":
    main()
