import csv
from pathlib import Path
import tempfile
import unittest

from scripts.resolve_trial_sites import resolve


class TrialSiteResolutionTests(unittest.TestCase):
    def test_maps_alias_to_official_filing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "sites.csv", root / "resolved.csv"
            source.write_text("facility_name,city_reported\n安医大一附院,合肥市\n未知研究中心,合肥市\n", encoding="utf-8")
            summary = resolve(source, target)
            self.assertEqual(summary["matched"], 1)
            with target.open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["filing_status"], "filed")
            self.assertTrue(rows[0]["official_hospital_id"].startswith("cnha-cfdi-"))
            self.assertEqual(rows[1]["resolution_status"], "unmatched")

    def test_bad_csv_shape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "sites.csv", root / "resolved.csv"
            source.write_text("facility_name\nHospital, University\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve(source, target)
