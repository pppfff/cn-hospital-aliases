import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from cn_hospital_aliases import HospitalRegistry

from scripts.audit_trial_site_coverage import audit


class TrialSiteCoverageAuditTests(unittest.TestCase):
    def test_audit_keeps_unmatched_names_out_of_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sites.csv.gz"
            with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["canonical_reported_name", "province_reported", "city_reported", "trial_count", "active_trial_count", "name_variants", "first_trial_id", "source_url"])
                writer.writeheader()
                writer.writerow({"canonical_reported_name": "安医大一附院", "province_reported": "安徽省", "city_reported": "合肥市", "trial_count": "3", "active_trial_count": "1", "name_variants": "安医大一附院", "first_trial_id": "NCT00000001", "source_url": "https://clinicaltrials.gov/study/NCT00000001"})
                writer.writerow({"canonical_reported_name": "未知研究中心", "province_reported": "安徽省", "city_reported": "合肥市", "trial_count": "4", "active_trial_count": "0", "name_variants": "未知研究中心", "first_trial_id": "NCT00000002", "source_url": "https://clinicaltrials.gov/study/NCT00000002"})
                writer.writerow({"canonical_reported_name": "安医大一附院", "province_reported": "错误省份", "city_reported": "错误城市", "trial_count": "2", "active_trial_count": "0", "name_variants": "安医大一附院", "first_trial_id": "NCT00000003", "source_url": "https://clinicaltrials.gov/study/NCT00000003"})
            output, queue, summary = root / "coverage.csv", root / "queue.csv", root / "summary.json"
            result = audit(source, output, queue, summary)
            self.assertEqual(result["matched_site_rows"], 1)
            self.assertEqual(result["matched_location_conflict_rows"], 1)
            self.assertEqual(result["unmatched_site_rows"], 1)
            self.assertEqual(json.loads(summary.read_text(encoding="utf-8"))["approval_effect"], "none; reported names remain review candidates")
            with queue.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["canonical_reported_name"], "未知研究中心")
            self.assertEqual(rows[1]["candidate_count"], "1")
            candidate = json.loads(rows[1]["candidates_json"])[0]
            self.assertEqual(candidate["official_name"], "安徽医科大学第一附属医院")
            with output.open(encoding="utf-8-sig", newline="") as handle:
                resolved = list(csv.DictReader(handle))
            self.assertEqual(resolved[2]["official_hospital_id"], "")
            self.assertEqual(resolved[2]["filing_number"], "")
            self.assertTrue(resolved[0]["official_hospital_id"])

    def test_ambiguous_name_survives_rejected_location(self):
        hospital = HospitalRegistry.load_default().resolve("安医大一附院")[0].hospital
        registry = HospitalRegistry([hospital, replace(hospital, hospital_id="test-other")])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sites.csv.gz"
            with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
                handle.write("canonical_reported_name,province_reported,city_reported,trial_count\n安医大一附院,错误省份,错误城市,2\n")
            with patch.object(HospitalRegistry, "load_default", return_value=registry):
                result = audit(source, root / "coverage.csv", root / "queue.csv", root / "summary.json")
            self.assertEqual(result["ambiguous_site_rows"], 1)
            with (root / "queue.csv").open(encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["candidate_count"], "2")
            self.assertEqual(len(json.loads(row["candidates_json"])), 2)
