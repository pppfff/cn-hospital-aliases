import unittest

from cn_hospital_aliases import normalize_name


class NormalizeNameTests(unittest.TestCase):
    def test_unicode_width_whitespace_and_punctuation(self) -> None:
        self.assertEqual(
            normalize_name("  北京（协和）医院－Ａ  "),
            normalize_name("北京协和医院-A"),
        )

    def test_semantic_words_are_preserved(self) -> None:
        self.assertNotEqual(normalize_name("省人民医院"), normalize_name("市人民医院"))

    def test_non_string_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            normalize_name(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

