import unittest

from cn_hospital_aliases import (
    Alias,
    AmbiguousNameError,
    Hospital,
    HospitalRegistry,
    NotFoundError,
)


class DefaultRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = HospitalRegistry.load_seed()

    def test_exact_alias_resolution(self) -> None:
        match = self.registry.get_one("哈医大三院")
        self.assertEqual(match.hospital.canonical_name, "哈尔滨医科大学附属肿瘤医院")
        self.assertEqual(match.match_type, "alias")
        self.assertEqual(match.alias_kind, "common_short_name")

    def test_historical_name_resolution(self) -> None:
        match = self.registry.get_one("广慈医院")
        self.assertEqual(match.hospital.canonical_name, "上海交通大学医学院附属瑞金医院")
        self.assertEqual(match.alias_kind, "historical_name")

    def test_canonical_name_resolution(self) -> None:
        match = self.registry.get_one("北京协和医院")
        self.assertEqual(match.match_type, "canonical")

    def test_location_filter(self) -> None:
        self.assertEqual(
            self.registry.resolve("北京儿童医院", province="上海市"), []
        )

    def test_fuzzy_is_opt_in(self) -> None:
        query = "华西医科大学附属一院"
        self.assertEqual(self.registry.resolve(query), [])
        matches = self.registry.resolve(query, fuzzy=True, min_score=0.7)
        self.assertTrue(matches)
        self.assertEqual(matches[0].hospital.canonical_name, "四川大学华西医院")
        self.assertEqual(matches[0].match_type, "fuzzy")

    def test_get_one_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.registry.get_one("不存在医院")

    def test_default_data_has_no_collisions(self) -> None:
        self.assertEqual(self.registry.alias_collisions(), {})


class AmbiguityTests(unittest.TestCase):
    def test_reference_identifiers_and_bilingual_locations(self):
        hospital = Hospital(hospital_id="cnha-example", canonical_name="示例医院", province="北京市", city="北京市", source_url="https://example.org", accessed_at="2026-09-05", city_aliases=("Beijing", "北京"), province_aliases=("Beijing",), identifiers=({"scheme": "ror", "value": "https://ror.org/example", "source_url": "https://ror.org/example"},))
        registry = HospitalRegistry([hospital])
        self.assertEqual(registry.get_one("示例医院", city="beijing", province="Beijing").hospital, hospital)
        self.assertEqual(registry.resolve_identifier("ror", "https://ror.org/example"), (hospital,))
        self.assertEqual(registry.resolve_identifier("hospital_id", hospital.hospital_id), (hospital,))
        self.assertEqual(registry.resolve_identifier("ror", "missing"), ())

    def test_same_alias_returns_both_hospitals(self) -> None:
        source = "https://example.org/source"
        hospitals = [
            Hospital(
                hospital_id="cnha-a",
                canonical_name="甲医院",
                province="甲省",
                city="甲市",
                source_url=source,
                accessed_at="2026-09-04",
                aliases=(Alias("中心医院", "common_short_name", source),),
            ),
            Hospital(
                hospital_id="cnha-b",
                canonical_name="乙医院",
                province="乙省",
                city="乙市",
                source_url=source,
                accessed_at="2026-09-04",
                aliases=(Alias("中心医院", "common_short_name", source),),
            ),
        ]
        registry = HospitalRegistry(hospitals)
        self.assertEqual(len(registry.resolve("中心医院")), 2)
        self.assertEqual(len(registry.resolve("中心医院", limit=1)), 2)
        self.assertEqual(len(registry.alias_collisions()), 1)
        with self.assertRaises(AmbiguousNameError):
            registry.get_one("中心医院")
        with self.assertRaises(AmbiguousNameError):
            registry.get_one("中心医院", limit=1)
        match = registry.get_one("中心医院", province="甲省")
        self.assertEqual(match.hospital.hospital_id, "cnha-a")


if __name__ == "__main__":
    unittest.main()
