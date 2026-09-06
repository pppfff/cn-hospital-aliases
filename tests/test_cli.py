import csv
from pathlib import Path
import tempfile
import unittest

from cn_hospital_aliases.cli import main


class BatchSafetyTests(unittest.TestCase):
    def test_unquoted_comma_is_rejected_before_writing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.csv", Path(directory) / "output.csv"
            source.write_text("hospital_name\nHospital, University\n", encoding="utf-8")
            self.assertEqual(main(["batch", str(source), str(output)]), 2)
            self.assertFalse(output.exists())

    def test_fuzzy_candidate_does_not_fill_an_approved_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.csv", Path(directory) / "output.csv"
            source.write_text("hospital_name\n华西医科大学附属一院\n", encoding="utf-8")
            result = main(["batch", str(source), str(output), "--fuzzy", "--min-score", "0.7", "--limit", "1"])
            self.assertEqual(result, 0)
            with output.open(encoding="utf-8-sig") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["_resolution_status"], "fuzzy_candidate")
            self.assertEqual(row["_hospital_id"], "")
            self.assertEqual(row["_canonical_name"], "")
