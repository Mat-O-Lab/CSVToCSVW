"""Tests for annotator.get_encoding. Run: python -m unittest discover -s tests"""
import codecs
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from annotator import get_encoding  # noqa: E402

GERMAN = "Größe;Preis\nMaße;12,5 €\nÄpfel;3,20 €\n" * 20
UNITS = (
    "Prüfgeschwindigkeit [mm/s];Temperatur [°C];Fläche [mm²];Länge [µm];Volumen [cm³]\n"
    + "".join(f"Probe {i};{20 + i / 3:.1f};{i * 1.5:.2f};{i};{i * 2}\n".replace(".", ",") for i in range(40))
)


def roundtrip(data: bytes) -> str:
    return data.decode(get_encoding(data))


class GetEncodingTest(unittest.TestCase):
    def test_ascii_and_empty(self):
        self.assertEqual(get_encoding(b"a;b\n1;2\n"), "utf-8")
        self.assertEqual(get_encoding(b""), "utf-8")

    def test_utf8(self):
        self.assertEqual(get_encoding(GERMAN.encode("utf-8")), "utf-8")

    def test_utf8_short_file_not_misdetected(self):
        data = "Einspannlänge\t832\n".encode("utf-8")
        self.assertEqual(roundtrip(data), "Einspannlänge\t832\n")

    def test_utf8_bom_is_stripped(self):
        data = b"\xef\xbb\xbf" + GERMAN.encode("utf-8")
        self.assertEqual(get_encoding(data), "utf-8-sig")
        self.assertEqual(roundtrip(data), GERMAN)

    def test_utf16_bom(self):
        self.assertEqual(roundtrip(GERMAN.encode("utf-16")), GERMAN)

    def test_cp1252_german_with_euro(self):
        self.assertEqual(roundtrip(GERMAN.encode("cp1252")), GERMAN)

    def test_cp1252_unit_characters(self):
        self.assertEqual(roundtrip(UNITS.encode("cp1252")), UNITS)

    def test_short_latin1_file_falls_back_to_western(self):
        # too short for statistical detection; regression: chardet 7 said iso8859-3
        data = b'"Einspannl\xe4nge"\t832.756\t"mm"\n"Messl\xe4nge"\t"nicht bekannt"\n'
        self.assertEqual(codecs.lookup(get_encoding(data)).name, "cp1252")
        self.assertIn("Einspannlänge", roundtrip(data))

    def test_cyrillic_cp1251(self):
        text = "Температура [°C];давление [МПа]\n" * 20
        self.assertEqual(roundtrip(text.encode("cp1251")), text)

    def test_cp1252_undefined_byte_falls_back_to_latin1(self):
        data = b"a;b\n\x81;\xe4\n"  # 0x81 undefined in cp1252
        self.assertEqual(get_encoding(data), "latin-1")
        data.decode("latin-1")

    def test_result_always_decodes(self):
        for sample in (GERMAN, UNITS):
            for enc in ("utf-8", "cp1252", "utf-16"):
                data = sample.encode(enc)
                data.decode(get_encoding(data))


if __name__ == "__main__":
    unittest.main()
