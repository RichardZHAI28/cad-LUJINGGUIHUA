import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.vendor'))
import unittest
from shapely.geometry import box,LineString
from weld_sequence import order_weld_paths,start_near_origin
from robot_adapters import defaults,render_script,BRANDS

class SequenceTests(unittest.TestCase):
    def test_descending_q_tail_does_not_jump_ahead_of_same_row(self):
        # Q is on the right but extends below the shared baseline.
        boxes=[box(80,0,100,40),box(0,10,20,40),box(40,10,60,40),box(0,60,20,90)]
        boundaries=[list(p.exterior.coords) for p in boxes]
        paths=[[(p.bounds[0]+1,p.bounds[1]+1),(p.bounds[0]+9,p.bounds[1]+1)] for p in boxes]
        for mode in ('centerline','outline','fill'):
            ordered=order_weld_paths(paths,boundaries,mode,1)
            self.assertEqual([p[0][0] for p in ordered],[1,41,81,1])
            for brand in BRANDS:
                script=render_script(ordered,0,20,10,defaults(brand))
                positions=[script.index('%.9f,%.9f,0.020000000'%(p[0][0]/1000,p[0][1]/1000)) for p in ordered]
                self.assertEqual(positions,sorted(positions))

    def test_positive_axes_precede_negative_coordinates(self):
        boxes=[box(-20,0,-10,10),box(30,0,40,10),box(0,-20,10,-10),box(0,30,10,40),box(0,0,10,10)]
        boundaries=[list(p.exterior.coords) for p in boxes]
        paths=[[(p.bounds[0]+1,p.bounds[1]+1),(p.bounds[0]+2,p.bounds[1]+1)] for p in boxes]
        ordered=order_weld_paths(paths,boundaries,'fill',1)
        self.assertEqual([p[0] for p in ordered],[(1,1),(31,1),(-19,1),(1,31),(1,-19)])

    def test_scrambled_entities_order_x_then_y_for_both_robots(self):
        boxes=[box(40,30,50,40),box(20,0,30,10),box(0,30,10,40),box(0,0,10,10)]
        boundaries=[list(p.exterior.coords) for p in boxes]
        paths=[[(p.bounds[0]+1,p.bounds[1]+1),(p.bounds[0]+9,p.bounds[1]+1)] for p in boxes]
        ordered=order_weld_paths(paths,boundaries,'centerline',1)
        self.assertEqual([p[0] for p in ordered],[(1,1),(21,1),(1,31),(41,31)])
        for brand in BRANDS:
            script=render_script(ordered,0,20,10,defaults(brand))
            positions=[script.index('%.9f,%.9f,0.020000000'%(p[0][0]/1000,p[0][1]/1000)) for p in ordered]
            self.assertEqual(positions,sorted(positions))

    def test_row_tolerance_groups_slight_baseline_variations(self):
        boxes=[box(0,2,10,12),box(20,0,30,10),box(0,30,10,40)]
        bounds=[list(p.exterior.coords) for p in boxes]
        paths=[[(1,3),(9,3)],[(21,1),(29,1)],[(1,31),(9,31)]]
        self.assertEqual(order_weld_paths(paths,bounds,'centerline',5),paths)

    def test_fill_preserves_direction_and_continuous_path(self):
        boundaries=[list(box(0,0,10,10).exterior.coords),list(box(20,0,30,10).exterior.coords)]
        right=[[(21,9),(29,9),(29,7),(21,7)],[(21,3),(29,3)]]
        left=[[(1,9),(9,9)],[(9,1),(1,1)]]
        self.assertEqual(order_weld_paths(right+left,boundaries,'fill'),left+right)

    def test_closed_start_and_open_orientation_preserve_geometry(self):
        ring=list(box(10,10,20,20).exterior.coords)
        changed=start_near_origin(ring)
        self.assertEqual(changed[0],(10,10))
        self.assertEqual(changed[0],changed[-1])
        self.assertTrue(LineString(ring).equals(LineString(changed)))
        self.assertEqual(start_near_origin([(20,0),(1,0)]),[(1,0),(20,0)])

    def test_negative_coordinates_start_from_origin_side(self):
        bounds=[list(box(-50,0,-40,10).exterior.coords),list(box(-20,0,-10,10).exterior.coords)]
        paths=[[(-49,1),(-41,1)],[(-19,1),(-11,1)]]
        result=order_weld_paths(paths,bounds,'centerline')
        self.assertEqual(result[0][0],(-11,1))
        self.assertEqual(result[1][0],(-41,1))

if __name__=='__main__':unittest.main()
