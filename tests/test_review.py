import csv
import tempfile
import unittest
from pathlib import Path

from cn_hospital_aliases import Hospital, HospitalRegistry
from cn_hospital_aliases.review import verification_register, chinese_name_reviews, institution_confirmation_register


class VerificationRegisterTests(unittest.TestCase):
    def test_chinese_decisions_require_explicit_approval_and_matching_filing(self):
        filing = {"companyId": "X", "compName": "示例医院（示例第二医院）", "source_url": "https://example.org/filing"}
        row = {"hospital_id": "cnha-cfdi-x", "official_name": filing["compName"],
               "source_url": filing["source_url"], "accessed_at": "2026-09-05",
               "candidate_alias": "示例第二医院", "decision": "retain_unapproved"}
        self.assertEqual(chinese_name_reviews({"decisions": [row]}, [filing]), [])
        row["decision"] = "approve_parallel_hospital_name"
        self.assertEqual(len(chinese_name_reviews({"decisions": [row]}, [filing])), 1)
        row["candidate_alias"] = "另一个医院"
        with self.assertRaises(ValueError):
            chinese_name_reviews({"decisions": [row]}, [filing])

    def test_identity_confirmation_does_not_require_english(self):
        filing = {"companyId": "X", "compName": "示例医院", "recordNo": "filing-x",
                  "source_url": "https://example.org/filing", "accessed_at": "2026-09-05"}
        registry = HospitalRegistry([Hospital(hospital_id="cnha-cfdi-x", canonical_name="示例医院",
            province="北京", city="北京", source_url=filing["source_url"], accessed_at="2026-09-05",
            filing_number="filing-x", filing_status="filed")])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "alias_review_queue.csv").write_text("hospital_id,candidate_alias\ncnha-cfdi-x,Unverified Hospital\n")
            result = institution_confirmation_register(directory, registry, [filing])
            self.assertEqual(result["filing_identities_confirmed"], 1)
            self.assertEqual(result["english_status_counts"], {"deferred_not_required_for_identity": 1})
            self.assertFalse(result["all_research_center_aliases_confirmed"])
            self.assertEqual(registry.resolve("Unverified Hospital"), [])
            filing["recordNo"] = "changed"
            with self.assertRaises(ValueError):
                institution_confirmation_register(directory, registry, [filing])

    def test_chinese_parallel_names_keep_parent_and_branch_separate(self):
        registry = HospitalRegistry.load_default()
        self.assertEqual(registry.get_one("江苏省人民医院").hospital.canonical_name,
                         "南京医科大学第一附属医院（江苏省人民医院）")
        self.assertEqual(registry.get_one("江苏省人民医院浦口分院").hospital.canonical_name,
                         "南京市浦口人民医院(江苏省人民医院浦口分院)")
        self.assertEqual(registry.resolve("山东省肿瘤防治研究院"), [])
        self.assertTrue(registry.get_one("四川大学华西医院（四川省国际医院）").hospital.official_review_completed)

    def test_supplemental_chinese_reviews_preserve_filing_boundaries(self):
        registry = HospitalRegistry.load_default()
        suzhou = registry.get_one("南京大学医学院附属苏州医院").hospital
        self.assertEqual(suzhou.canonical_name, "苏州科技城医院")
        self.assertEqual(registry.get_one("南京鼓楼医院集团苏州医院").hospital.hospital_id, suzhou.hospital_id)
        self.assertFalse(any(match.hospital.hospital_id == suzhou.hospital_id
                             for match in registry.resolve("南京鼓楼医院")))
        self.assertEqual(registry.get_one("上海儿童医学中心").hospital.hospital_id,
                         "cnha-cfdi-44259fd7c0a80333772e83dcfca7e60f")
        self.assertEqual(registry.get_one("中国医学科学院阜外心血管病医院").hospital.canonical_name,
                         "中国医学科学院阜外医院")

    def test_affiliated_names_do_not_merge_managing_hospitals(self):
        registry = HospitalRegistry.load_default()
        nantong = registry.get_one("南通大学第二附属医院").hospital
        self.assertEqual(nantong.canonical_name, "南通市第一人民医院")
        self.assertEqual(registry.get_one("南通医学院第二附属医院").hospital.hospital_id, nantong.hospital_id)
        historical = next(a for a in nantong.aliases if a.name == "南通医学院第二附属医院")
        self.assertEqual((historical.kind, historical.valid_from, historical.valid_to),
                         ("historical_name", "1992", "2004"))
        self.assertNotEqual(registry.get_one("南通大学附属医院").hospital.hospital_id, nantong.hospital_id)
        airport = registry.get_one("四川大学华西空港医院").hospital
        self.assertEqual(airport.canonical_name, "成都市双流区第一人民医院")
        self.assertNotEqual(airport.hospital_id, registry.get_one("四川大学华西医院").hospital.hospital_id)
        self.assertEqual(registry.get_one("西湖大学医学院附属杭州市第一人民医院").hospital.canonical_name,
                         "杭州市第一人民医院（西湖大学附属杭州市第一人民医院）")
        self.assertEqual(registry.resolve("河南中医学院第一医院"), [])

    def test_rename_evidence_preserves_date_precision(self):
        registry = HospitalRegistry.load_default()
        ningbo = registry.get_one("中国科学院大学宁波华美医院").hospital
        self.assertEqual(ningbo.canonical_name, "宁波市第二医院")
        old = next(a for a in ningbo.aliases if a.name == "中国科学院大学宁波华美医院")
        self.assertEqual(old.kind, "historical_name")
        self.assertIsNone(old.valid_to)
        wuhan = registry.get_one("武汉普爱医院").hospital
        self.assertEqual(wuhan.hospital_id, "cnha-cfdi-2a76f77dc0a8033311314f9be1ed9183")
        old = next(a for a in wuhan.aliases if a.name == "汉口普爱医院")
        self.assertEqual((old.valid_from, old.valid_to), ("1864", "1958"))
        self.assertEqual(registry.resolve("广东药学院第一附属医院"), [])

    def test_reference_leads_never_approve_and_conflicts_have_no_id(self):
        registry = HospitalRegistry([Hospital(
            hospital_id="example", canonical_name="Example Hospital",
            province="Beijing", city="Beijing", source_url="https://example.org",
            accessed_at="2026-09-05", filing_number="example-filing",
        )])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            baseline = directory / "trial_site_review_baseline.csv"
            baseline.write_text(
                "canonical_reported_name,province_reported,city_reported,trial_count,source_url\n"
                "Example Hospital,Beijing,Beijing,1,https://example.org/trial\n"
                "Example Hospital,Shanghai,Shanghai,1,https://example.org/trial\n"
                "Reference Hospital,Beijing,Beijing,1,https://example.org/trial\n"
                "Unknown Hospital,Beijing,Beijing,1,https://example.org/trial\n",
                encoding="utf-8",
            )
            (directory / "approved_aliases.csv").write_text(
                "alias,hospital_id,source_url\nExample Hospital,example,https://example.org\n",
                encoding="utf-8",
            )
            (directory / "alias_review_queue.csv").write_text(
                "candidate_alias,hospital_id\nReference Hospital,example\n", encoding="utf-8",
            )
            original = baseline.read_bytes()
            summary = verification_register(directory, registry)
            with (directory / "trial_site_verification_register.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["official_hospital_id"], "example")
            self.assertEqual(rows[1]["name_verification_status"], "verified_name_relation")
            self.assertEqual(rows[1]["location_verification_status"], "requires_location_review")
            self.assertEqual(rows[1]["official_hospital_id"], "")
            self.assertEqual(rows[2]["name_verification_status"], "unverified_reference_only")
            self.assertEqual(rows[2]["official_hospital_id"], "")
            self.assertEqual(rows[3]["name_verification_status"], "unverified_no_approved_evidence")
            self.assertFalse(summary["all_name_relations_verified"])
            self.assertEqual(summary["new_manual_source_reviews_performed_by_script"], 0)
            self.assertEqual(baseline.read_bytes(), original)
            first_output = (directory / "trial_site_verification_register.csv").read_bytes()
            verification_register(directory, registry)
            self.assertEqual((directory / "trial_site_verification_register.csv").read_bytes(), first_output)
