"""Run integrity, uniqueness, provenance and trial-count reconciliation checks."""
import argparse
import csv
import json
from pathlib import Path
import sqlite3


def check(directory: Path) -> dict:
    metadata = json.loads((directory / "quality_summary.json").read_text(encoding="utf-8"))
    with sqlite3.connect(f"file:{directory / 'hospital_master.sqlite'}?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        count_mismatch = db.execute("""SELECT i.hospital_id FROM institutions i LEFT JOIN
          (SELECT hospital_id, COUNT(DISTINCT trial_id) n FROM trial_site_links
           WHERE source_registry='ClinicalTrials.gov' GROUP BY hospital_id) c
          ON c.hospital_id=i.hospital_id WHERE i.ctg_trial_count != COALESCE(c.n,0)""").fetchall()
        assert not count_mismatch, count_mismatch[:5]
        nmpa_mismatch = db.execute("""SELECT i.hospital_id FROM institutions i LEFT JOIN
          (SELECT hospital_id, COUNT(DISTINCT trial_id) n FROM trial_site_links
           WHERE source_registry='NMPA_CDE' GROUP BY hospital_id) c
          ON c.hospital_id=i.hospital_id WHERE i.nmpa_trial_count IS NOT NULL
          AND i.nmpa_trial_count != COALESCE(c.n,0)""").fetchall()
        assert not nmpa_mismatch, nmpa_mismatch[:5]
        duplicate_ids = db.execute("""SELECT scheme,value,COUNT(DISTINCT hospital_id) FROM identifiers
          WHERE scheme IN ('ror','cfdi_drug_filing','cfdi_company_id','cn_uscc')
          GROUP BY scheme,value HAVING COUNT(DISTINCT hospital_id)>1""").fetchall()
        assert not duplicate_ids, duplicate_ids[:5]
        for identifier in metadata["quarantined_ror_ids"]:
            assert not db.execute("SELECT * FROM identifiers WHERE value=?", (identifier,)).fetchall()
        assert not db.execute("SELECT * FROM names WHERE source_url='' OR accessed_at=''").fetchall()
        priority_count = db.execute("SELECT COUNT(*),COUNT(DISTINCT hospital_id) FROM review_priority").fetchone()
        rank_column = "ctg_trial_count" if metadata["ranking_basis"] == "ctg" else "nmpa_trial_count"
        expected_ids = [row[0] for row in db.execute(f"SELECT hospital_id FROM institutions WHERE {rank_column}>0 ORDER BY {rank_column} DESC,hospital_id LIMIT 1000")]
        expected_count = len(expected_ids)
        assert priority_count == (expected_count, expected_count), priority_count
        with (directory / "top1000_review.csv").open(encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        assert [row["hospital_id"] for row in csv_rows] == expected_ids
        assert [int(row[rank_column]) for row in csv_rows] == sorted([int(row[rank_column]) for row in csv_rows], reverse=True)
        summary = {
            "sqlite_integrity": "ok", "foreign_key_errors": 0, "trial_count_mismatches": 0, "nmpa_count_mismatches": 0,
            "duplicate_authoritative_identifiers": 0, "missing_name_evidence_rows": 0,
            "priority_rows": expected_count, "priority_unique_record_ids": expected_count,
            "quarantined_ror_id_in_master": False,
            "official_field_reviewed_entities": db.execute("SELECT COUNT(DISTINCT hospital_id) FROM names WHERE evidence_status='official_source_reviewed'").fetchone()[0],
            "rows_by_identity_status": dict(db.execute("SELECT verification_status,COUNT(*) FROM institutions GROUP BY verification_status").fetchall()),
            "nmpa_counts_unavailable_rows": db.execute("SELECT COUNT(*) FROM institutions WHERE nmpa_trial_count IS NULL").fetchone()[0],
            "warning": "Passing integrity checks does not certify all hospital identities or complete NMPA participation coverage.",
        }
    (directory / "validation_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/master"))
    print(json.dumps(check(parser.parse_args().directory), ensure_ascii=False, indent=2))
