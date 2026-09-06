import unittest

from cn_hospital_aliases import Hospital, HospitalRegistry
from cn_hospital_aliases.official import official_records


class OfficialIdentityTests(unittest.TestCase):
    def setUp(self):
        self.filings = [{"companyId": "EXAMPLE", "compName": "北京示例医院（北京示例医学院）", "recordNo": "药临床机构备字2020000000", "recordStatus": "8", "areaName": "北京市", "address": "北京市示例路1号", "source_url": "https://beian.cfdi.org.cn/CTMDS/", "accessed_at": "2026-09-05"}]
        self.ror = [{"id": "https://ror.org/example", "names": [{"value": "北京示例医院", "types": ["label"], "lang": "zh"}, {"value": "Beijing Example Hospital", "types": ["label", "ror_display"], "lang": "en"}], "locations": [{"geonames_details": {"country_code": "CN", "country_subdivision_code": "BJ", "name": "Beijing"}}], "links": [], "status": "active"}]

    def build(self, reviews=None):
        return official_records(self.filings, self.ror, reviews=reviews or [], decisions={}, accessed_at="2026-09-05", include_seed=False)

    def test_literal_filing_name_and_identity_are_preserved(self):
        records, names, _ = self.build()
        self.assertEqual(records[0]["canonical_name"], self.filings[0]["compName"])
        self.assertEqual(records[0]["filing_number"], self.filings[0]["recordNo"])
        self.assertTrue(all(row["hospital_id"] == "cnha-cfdi-example" for row in names))

    def test_split_components_in_filing_are_not_automatic_aliases(self):
        records, _, candidates = self.build()
        registry = HospitalRegistry(Hospital.from_dict(row) for row in records)
        self.assertEqual(registry.resolve("北京示例医学院"), [])
        self.assertTrue(any(row["candidate_alias"] == "北京示例医学院" for row in candidates))

    def test_reference_only_english_is_not_approved(self):
        records, _, candidates = self.build()
        registry = HospitalRegistry(Hospital.from_dict(row) for row in records)
        self.assertEqual(registry.resolve("Beijing Example Hospital"), [])
        self.assertEqual(records[0]["english_name"], "")
        self.assertTrue(any(row["candidate_alias"] == "Beijing Example Hospital" for row in candidates))

    def test_unfiled_ror_does_not_create_an_official_institution(self):
        self.ror[0]["names"][0]["value"] = "未备案示例医院"
        records, _, _ = self.build()
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["hospital_id"].startswith("cnha-cfdi-"))

    def test_primary_review_enables_alias_without_needing_trial_records(self):
        review = {"hospital_id": "cnha-cfdi-example", "names": [{"value": "Beijing Example Hospital", "kind": "english_name", "source_url": "https://example.org/official", "accessed_at": "2026-09-05"}]}
        records, _, candidates = self.build([review])
        registry = HospitalRegistry(Hospital.from_dict(row) for row in records)
        self.assertEqual(registry.get_one("Beijing Example Hospital").hospital.filing_number, self.filings[0]["recordNo"])
        self.assertFalse(any(row["candidate_alias"] == "Beijing Example Hospital" for row in candidates))
        self.assertIsNone(registry.hospitals[0].trial_count)

    def test_alias_access_date_survives_build_and_api_serialization(self):
        review = {"hospital_id": "cnha-cfdi-example", "names": [{"value": "Reviewed Name", "kind": "english_name", "source_url": "https://example.org/official", "accessed_at": "2026-09-06"}]}
        records, _, _ = self.build([review])
        registry = HospitalRegistry(Hospital.from_dict(row) for row in records)
        match = registry.get_one("Reviewed Name")
        self.assertEqual(match.hospital.accessed_at, "2026-09-05")
        self.assertEqual(match.to_dict()["hospital"]["aliases"][0]["accessed_at"], "2026-09-06")

    def test_cancelled_filing_retains_status_for_historical_resolution(self):
        self.filings[0]["recordStatus"] = "9"
        records, _, _ = self.build()
        self.assertEqual(records[0]["filing_status"], "cancelled")

    def test_default_registry_has_only_filing_anchors(self):
        registry = HospitalRegistry.load_default()
        self.assertTrue(all(h.hospital_id.startswith("cnha-cfdi-") and h.filing_number for h in registry.hospitals))
        self.assertEqual(registry.resolve("Clearly unregistered imaginary research site"), [])

    def test_municipality_spelling_does_not_hide_real_location_conflict(self):
        records, _, _ = self.build()
        registry = HospitalRegistry(Hospital.from_dict(row) for row in records)
        name = self.filings[0]["compName"]
        self.assertEqual(len(registry.resolve(name, province="Beijing Municipality")), 1)
        self.assertEqual(registry.resolve(name, province="Shanghai Municipality"), [])

    def test_reviewed_names_preserve_separately_filed_branches(self):
        registry = HospitalRegistry.load_default()
        pairs = [
            ("Cancer Hospital Chinese Academy of Medical Sciences", "中国医学科学院肿瘤医院"),
            ("Ruijin Hospital, Shanghai Jiaotong University School of Medicine", "上海交通大学医学院附属瑞金医院"),
            ("Tianjin Medical University General Hospital", "天津医科大学总医院"),
            ("Tianjin Medical University Cancer Institute and Hospital", "天津市肿瘤医院（天津医科大学肿瘤医院）"),
        ]
        for alias, canonical in pairs:
            with self.subTest(alias=alias):
                self.assertEqual(registry.get_one(alias).hospital.canonical_name, canonical)
        self.assertEqual(registry.resolve("Cancer Hospital Chinese Academy of Medical Sciences", city="Shenzhen"), [])
        self.assertNotEqual(registry.get_one("天津医科大学总医院空港医院").hospital.hospital_id,
                            registry.get_one("Tianjin Medical University General Hospital").hospital.hospital_id)

    def test_zhejiang_numbered_hospitals_and_cmu_college_remain_separate(self):
        registry = HospitalRegistry.load_default()
        first = registry.get_one("The First Affiliated Hospital, Zhejiang University School of Medicine").hospital
        second = registry.get_one("The Second Affiliated Hospital Zhejiang University School of Medicine").hospital
        self.assertEqual(first.canonical_name, "浙江大学医学院附属第一医院")
        self.assertEqual(second.canonical_name, "浙江大学医学院附属第二医院")
        self.assertNotEqual(first.hospital_id, second.hospital_id)
        self.assertEqual(registry.get_one("The First Hospital of China Medical University").hospital.canonical_name,
                         "中国医科大学附属第一医院")
        self.assertEqual(registry.resolve("中国医科大学第一临床学院"), [])
