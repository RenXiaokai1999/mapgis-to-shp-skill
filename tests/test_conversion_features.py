"""Regression tests for blank MapGIS attributes and polygon repair policy."""

import importlib.util
import unittest
from pathlib import Path

from shapely.geometry import Polygon


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mapgis_to_shp.py"
spec = importlib.util.spec_from_file_location("mapgis_to_shp", SCRIPT)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class ConversionFeaturesTest(unittest.TestCase):
    def test_inactive_attribute_rows_are_identified_without_dropping_geometry(self):
        raw = bytes([0, 1, 0, 1])
        self.assertEqual(converter.inactive_attribute_ids(raw, 0, 1, [1, 2, 3]), [2])

    def test_material_polygon_repair_requires_opt_in(self):
        bowtie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0)])
        with self.assertRaisesRegex(ValueError, "materially changed area"):
            converter.repair_polygon(bowtie, allow_material=False)
        fixed, detail = converter.repair_polygon(bowtie, allow_material=True)
        self.assertTrue(fixed.is_valid)
        self.assertFalse(fixed.is_empty)
        self.assertGreater(detail["absolute_area_change"], 0)

    def test_valid_polygon_is_not_changed(self):
        original = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        fixed, detail = converter.repair_polygon(original, allow_material=True)
        self.assertIs(fixed, original)
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
