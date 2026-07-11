import unittest
from app.utils.normalization import clean_street_name, normalize_house, extract_numeric_part

class TestNormalization(unittest.TestCase):
    def test_clean_street_name(self):
        self.assertEqual(clean_street_name("вулиця Вишнева (Солом'янський р-н)"), "Вишнева")
        self.assertEqual(clean_street_name("пров. Шевченка"), "Шевченка")
        self.assertEqual(clean_street_name("  проспект   Перемоги  "), "Перемоги")
        self.assertEqual(clean_street_name(""), "")
        self.assertEqual(clean_street_name(None), "")

    def test_normalize_house(self):
        self.assertEqual(normalize_house("12-б"), "12б")
        self.assertEqual(normalize_house("1/2"), "12")
        self.assertEqual(normalize_house("Академіка Палладіна, 15"), "академікапалладіна15")
        self.assertEqual(normalize_house(""), "")
        self.assertEqual(normalize_house(None), "")

    def test_extract_numeric_part(self):
        self.assertEqual(extract_numeric_part("12-б"), 12)
        self.assertEqual(extract_numeric_part("б/н"), 1)
        self.assertEqual(extract_numeric_part("149/1"), 149)
        self.assertEqual(extract_numeric_part(""), 1)
        self.assertEqual(extract_numeric_part(None), 1)

if __name__ == "__main__":
    unittest.main()
