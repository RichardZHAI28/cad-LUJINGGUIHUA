import math
import unittest
from geometry import discretize, transform, urscript

class GeometryTests(unittest.TestCase):
    def test_spacing_and_endpoints(self):
        path = discretize([(0, 0), (3, 4), (3, 4), (6, 4)], 0.7)
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (6, 4))
        self.assertTrue(all(math.hypot(b[0]-a[0], b[1]-a[1]) <= 0.700001 for a, b in zip(path, path[1:])))

    def test_user_origin_rotation(self):
        self.assertEqual(transform((10, 20), (10, 20), 45, 2), (0, 0))
        x, y = transform((11, 20), (10, 20), 90, 2)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 2)

    def test_ur_units_and_arc_sequence(self):
        script = urscript([[(100, 200), (110, 200)], [(120, 200), (130, 200)]], 2, 20, 10, 3)
        self.assertIn('p[0.100000,0.200000,0.020000', script)
        self.assertIn('v=0.010000', script)
        self.assertEqual(script.count('set_standard_digital_out(3, True)'), 2)
        first_on = script.index('set_standard_digital_out(3, True)')
        first_off = script.index('set_standard_digital_out(3, False)', first_on)
        self.assertLess(first_off, script.index('p[0.110000,0.200000,0.020000'))

    def test_seam_transfer_lifts_before_xy_then_descends_before_arc(self):
        # Work at Z=5 mm and manually request a 20 mm lift.
        script = urscript([[(0, 0), (10, 0)], [(30, 40), (35, 40)]], 5, 5+20, 10, 0)
        commands = [line.strip() for line in script.splitlines() if not line.strip().startswith('#')]
        end = next(i for i, line in enumerate(commands) if 'p[0.010000,0.000000,0.005000' in line)
        transition = commands[end:end+7]
        self.assertIn('p[0.010000,0.000000,0.005000', transition[0])
        self.assertEqual(transition[1], 'set_standard_digital_out(0, False)')
        self.assertIn('p[0.010000,0.000000,0.025000', transition[2])
        self.assertIn('p[0.030000,0.040000,0.025000', transition[3])
        self.assertIn('p[0.030000,0.040000,0.005000', transition[4])
        self.assertEqual(transition[5], 'set_standard_digital_out(0, True)')
        self.assertIn('p[0.035000,0.040000,0.005000', transition[6])
        self.assertIn('p[0.035000,0.040000,0.025000', commands[-3])

if __name__ == '__main__':
    unittest.main()
