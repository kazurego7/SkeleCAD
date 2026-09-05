"""Guard positive-volume STL validation without creating test mesh files."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import validate_stl


class STLValidationTests(unittest.TestCase):
    def setUp(self):
        origin, x, y, z = (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)
        self.triangles = [(origin, y, x), (origin, x, z), (origin, z, y), (x, y, z)]

    def analyse(self, triangles):
        with patch.object(validate_stl, "load_triangles", return_value=triangles):
            return validate_stl.analyse(Path("fixture.stl"))

    def test_outward_closed_solid_passes(self):
        result = self.analyse(self.triangles)
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["signed_volume_mm3"], 1 / 6)

    def test_inward_closed_solid_fails(self):
        result = self.analyse([(a, c, b) for a, b, c in self.triangles])
        self.assertTrue(result["closed_two_manifold"])
        self.assertLess(result["signed_volume_mm3"], 0)
        self.assertFalse(result["passed"])

    def test_open_solid_fails(self):
        self.assertFalse(self.analyse(self.triangles[:-1])["passed"])


if __name__ == "__main__":
    unittest.main()
