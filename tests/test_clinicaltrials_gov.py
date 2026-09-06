from pathlib import Path
import tempfile
import unittest

from cn_hospital_aliases.sources.clinicaltrials_gov import (
    aggregate_sites,
    classify_facility,
    extract_mentions,
    generate_alias_candidates,
    write_csv_gz,
)


FIXTURE = Path(__file__).parent / "fixtures/clinicaltrials_page.json"


class ClinicalTrialsGovTests(unittest.TestCase):
    def test_extracts_only_china_locations_with_facilities(self) -> None:
        mentions = extract_mentions([FIXTURE])
        self.assertEqual(len(mentions), 3)
        self.assertTrue(all(row["country"] == "China" for row in mentions))

    def test_aggregates_presentation_variants(self) -> None:
        sites = aggregate_sites(extract_mentions([FIXTURE]))
        hospital = next(site for site in sites if site["facility_type_guess"] == "hospital")
        self.assertEqual(hospital["trial_count"], 2)
        self.assertEqual(hospital["active_trial_count"], 1)
        self.assertEqual(hospital["name_variant_count"], 2)

    def test_classification_is_conservative(self) -> None:
        self.assertEqual(classify_facility("某大学附属医院"), "hospital")
        self.assertEqual(classify_facility("Cancer Medical Center"), "hospital")
        self.assertEqual(classify_facility("Site 002"), "non_specific")
        self.assertEqual(classify_facility("某研究所"), "other_facility")

    def test_alias_candidate_pairs_are_not_auto_merged(self) -> None:
        sites = [
            {
                "site_id": "a",
                "canonical_reported_name": "北京示例大学附属第一医院",
                "province_reported": "北京市",
                "city_reported": "北京市",
            },
            {
                "site_id": "b",
                "canonical_reported_name": "北京示例大学第一附属医院",
                "province_reported": "北京市",
                "city_reported": "北京市",
            },
        ]
        candidates = generate_alias_candidates(sites, min_score=0.8)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["decision"], "manual_review")

    def test_empty_csv_snapshot_keeps_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.csv.gz"
            write_csv_gz(path, [], fieldnames=["hospital_id", "name"])
            import gzip

            with gzip.open(path, "rt", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "hospital_id,name\n")


if __name__ == "__main__":
    unittest.main()
