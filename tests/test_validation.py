import unittest

from cn_hospital_aliases import Alias, Hospital, HospitalRegistry
from cn_hospital_aliases.validation import validate_hospitals


class ValidationTests(unittest.TestCase):
    def test_zero_observed_trials_and_legacy_http_evidence_are_explicit(self):
        hospital = Hospital(hospital_id="cnha-example", canonical_name="示例医院", province="省", city="市", source_url="http://example.org", accessed_at="2026-09-05", trial_count=0)
        report = validate_hospitals((hospital,))
        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)

    def test_default_dataset_is_valid(self) -> None:
        registry = HospitalRegistry.load_seed()
        report = validate_hospitals(registry.hospitals)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, ())

    def test_collision_is_warning_not_error(self) -> None:
        source = "https://example.org/source"
        hospitals = tuple(
            Hospital(
                hospital_id=f"cnha-{index}",
                canonical_name=f"医院{index}",
                province="省",
                city="市",
                source_url=source,
                accessed_at="2026-09-04",
                aliases=(Alias("同名医院", "common_short_name", source),),
            )
            for index in range(2)
        )
        report = validate_hospitals(hospitals)
        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)


if __name__ == "__main__":
    unittest.main()
