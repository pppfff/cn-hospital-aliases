import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cn_hospital_aliases.master import apply_reviews, build_master, expand_website_reviews, filing_names, link_mentions, reference_entities
from cn_hospital_aliases.sources.nmpa import parse_detail_html, read_participation_csv, validate_participation


def references():
    filings = [{"companyId": "EXAMPLE", "compName": "北京示例医院（北京示例医学院）", "areaName": "北京市", "address": "北京市示例路1号", "recordNo": "药临床机构备字2020000000", "recordStatus": "8", "source_url": "https://beian.cfdi.org.cn/CTMDS/apps/pub/drugPublic1.jsp", "accessed_at": "2026-09-05"}]
    ror = [{"id": "https://ror.org/example", "names": [{"value": "北京示例医院", "lang": "zh", "types": ["label"]}, {"value": "Beijing Example Hospital", "lang": "en", "types": ["label", "ror_display"]}], "locations": [{"geonames_details": {"country_code": "CN", "country_subdivision_code": "BJ", "name": "Beijing"}}], "links": [], "status": "active"}]
    return filings, ror


def mention(trial="NCT00000001", city="Beijing", province="", name="Beijing Example Hospital"):
    return {"source_registry": "ClinicalTrials.gov", "trial_id": trial, "facility_name": name, "city_reported": city, "province_reported": province, "source_url": "https://clinicaltrials.gov/study/" + trial}


class MasterTests(unittest.TestCase):
    def test_explicit_website_crosswalk_retains_field_scope(self):
        links, reviews = expand_website_reviews({"accessed_at": "2026-09-05", "review_scope": "Chinese title and identity only", "reviewed_links": [{"ror_id": "https://ror.org/example", "cfdi_company_id": "EXAMPLE", "official_name_zh": "北京示例医院", "source_url": "https://example.org"}]})
        self.assertEqual(links[0]["source_urls"], ["https://example.org"])
        self.assertFalse(reviews[0]["official_review_completed"])
        self.assertEqual(reviews[0]["names"][0]["kind"], "official_variant")

    def test_chinese_display_name_is_not_an_english_translation(self):
        filings, ror = references()
        ror[0]["names"] = ror[0]["names"][:1]
        entities = reference_entities(filings, ror, accessed_at="2026-09-05")
        self.assertEqual(entities["cnha-cfdi-example"]["english_name"], "")

    def test_complete_review_requires_requested_evidence(self):
        entities = reference_entities(*references(), accessed_at="2026-09-05")
        with self.assertRaises(ValueError):
            apply_reviews(entities, [{"hospital_id": "cnha-cfdi-example", "official_review_completed": True}])

    def test_reviewed_names_keep_evidence_and_enable_exact_link(self):
        entities = reference_entities(*references(), accessed_at="2026-09-05")
        apply_reviews(entities, [{"hospital_id": "cnha-cfdi-example", "names": [{"value": "Example University Hospital", "kind": "english_name", "source_url": "https://example.org/hospital", "accessed_at": "2026-09-05"}]}])
        links, _ = link_mentions(entities, [mention(name="Example University Hospital")])
        self.assertEqual(links[0]["link_method"], "exact_reference_name_and_city")
        self.assertEqual(entities["cnha-cfdi-example"]["english_name"], "Example University Hospital")
        self.assertFalse(entities["cnha-cfdi-example"]["official_review_completed"])

    def test_official_parallel_names_include_clinical_school_but_preserve_campus(self):
        self.assertEqual(filing_names("北京示例医院（北京示例医学院）"), ["北京示例医院", "北京示例医学院"])
        self.assertEqual(filing_names("北京示例医院（东院区）"), ["北京示例医院（东院区）"])

    def test_exact_reference_link_and_unique_trials(self):
        entities = reference_entities(*references(), accessed_at="2026-09-05")
        links, counts = link_mentions(entities, [mention(), mention(province="Beijing Municipality"), mention("NCT00000002")])
        self.assertEqual(len(entities), 1)
        self.assertEqual({row["hospital_id"] for row in links}, {"cnha-cfdi-example"})
        self.assertEqual(len(counts["cnha-cfdi-example"]["ClinicalTrials.gov"]), 2)

    def test_conflicting_province_or_city_is_not_linked(self):
        entities = reference_entities(*references(), accessed_at="2026-09-05")
        links, _ = link_mentions(entities, [mention(province="Guangdong"), mention(city="Shanghai")])
        self.assertTrue(all(row["link_method"] == "unresolved" for row in links))

    def test_high_similarity_is_not_identity(self):
        entities = reference_entities(*references(), accessed_at="2026-09-05")
        links, _ = link_mentions(entities, [mention(name="Beijing Example Hospitals")])
        self.assertEqual(links[0]["link_method"], "unresolved")

    def test_quarantine_excludes_conflicting_reference_names(self):
        entities = reference_entities(*references(), accessed_at="2026-09-05", decisions={"quarantine_ror": [{"ror_id": "https://ror.org/example"}]})
        links, _ = link_mentions(entities, [mention()])
        self.assertEqual(links[0]["link_method"], "unresolved")
        self.assertFalse(any(identifier["scheme"] == "ror" for entity in entities.values() for identifier in entity["identifiers"]))

    def test_database_counts_and_unavailable_nmpa_are_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            result = build_master(*references(), [mention(), mention(province="Beijing"), mention("NCT00000002")], output_dir=path, package_output=path / "package.jsonl.gz", reviews=[], nmpa_records_available=False, accessed_at="2026-09-05")
            self.assertIsNone(result["nmpa_trial_ids_in_input"])
            with closing(sqlite3.connect(path / "hospital_master.sqlite")) as database:
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(database.execute("SELECT ctg_trial_count,nmpa_trial_count FROM institutions").fetchone(), (2, None))
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_nmpa_ranking_requires_and_counts_ctr_records_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            nmpa = {**mention("CTR20260001"), "source_registry": "NMPA_CDE"}
            result = build_master(*references(), [mention(), nmpa, nmpa], output_dir=path, package_output=path / "package.jsonl.gz", reviews=[], nmpa_records_available=True, accessed_at="2026-09-05", rank_by="nmpa")
            self.assertEqual(result["nmpa_trial_ids_in_input"], 1)
            with closing(sqlite3.connect(path / "hospital_master.sqlite")) as database:
                self.assertEqual(database.execute("SELECT ctg_trial_count,nmpa_trial_count FROM institutions").fetchone(), (1, 1))
            with self.assertRaises(ValueError):
                build_master(*references(), [mention()], output_dir=path, package_output=path / "package.jsonl.gz", reviews=[], nmpa_records_available=False, accessed_at="2026-09-05", rank_by="nmpa")


class NmpaTests(unittest.TestCase):
    def test_mismatched_url_id_and_missing_name_are_rejected(self):
        row = {"trial_id": "CTR20260001", "facility_name": "北京示例医院", "source_url": "https://www.chinadrugtrials.org.cn/clinicaltrials.searchlistdetail.dhtml?reg_no=CTR20260002", "accessed_at": "2026-09-05"}
        with self.assertRaises(ValueError):
            validate_participation(row)
        with self.assertRaises(ValueError):
            validate_participation({**row, "facility_name": None})

    def test_validates_ctr_and_specific_official_detail_evidence(self):
        row = {"trial_id": "CTR20260001", "facility_name": "北京示例医院", "source_url": "https://www.chinadrugtrials.org.cn/clinicaltrials.searchlistdetail.dhtml?reg_no=CTR20260001", "accessed_at": "2026-09-05"}
        self.assertEqual(validate_participation(row)["source_registry"], "NMPA_CDE")
        for invalid in ({**row, "trial_id": "NCT00000001"}, {**row, "source_url": "https://beian.cfdi.org.cn/CTMDS/"}, {**row, "source_url": "https://www.chinadrugtrials.org.cn/"}):
            with self.assertRaises(ValueError):
                validate_participation(invalid)

    def test_only_explicit_china_participating_rows_are_imported(self):
        html = """<p>登记号 CTR20260001</p><table><tr><th>机构名称</th><th>研究者</th><th>国家</th><th>省（州）</th><th>城市</th></tr><tr><td>北京示例医院</td><td>某研究者</td><td>中国</td><td>北京市</td><td>北京市</td></tr><tr><td>Foreign Hospital</td><td>Investigator</td><td>美国</td><td>NY</td><td>New York</td></tr></table>"""
        rows = parse_detail_html(html, source_url="https://www.chinadrugtrials.org.cn/clinicaltrials.searchlistdetail.dhtml?reg_no=CTR20260001", accessed_at="2026-09-05")
        self.assertEqual(len(rows), 1)
        self.assertNotIn("研究者", json.dumps(rows, ensure_ascii=False))

    def test_challenge_or_missing_table_is_an_error(self):
        for html in ("<script>challenge()</script>", "<p>CTR20260001</p><p>No participating sites</p>"):
            with self.assertRaises(ValueError):
                parse_detail_html(html, source_url="https://www.chinadrugtrials.org.cn/clinicaltrials.searchlistdetail.dhtml", accessed_at="2026-09-05")

    def test_empty_template_is_not_a_claim_of_complete_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.csv"
            path.write_text("trial_id,facility_name,source_url,accessed_at\n", encoding="utf-8")
            self.assertEqual(read_participation_csv(path), [])


if __name__ == "__main__":
    unittest.main()
