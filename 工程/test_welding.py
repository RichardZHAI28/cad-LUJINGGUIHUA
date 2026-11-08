import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '.vendor'))
import unittest
import math
from shapely.geometry import Polygon, LineString, Point, box
from shapely.affinity import scale, rotate,translate
from welding import plan_paths, solid_region, minimum_trails, FILL_MODES,straight_priority_trails,centerline_encloses_holes,connected_weld_trails

OUTER = [(0,0),(30,0),(30,20),(0,20),(0,0)]
HOLE = [(10,5),(20,5),(20,15),(10,15),(10,5)]

class WeldingTests(unittest.TestCase):
    def test_equal_distance_curved_stroke_caps_and_rotation(self):
        arc=LineString([(20*math.cos(-2.3+i*4.6/160),20*math.sin(-2.3+i*4.6/160)) for i in range(161)])
        shape=arc.buffer(2,cap_style=2)
        for angle in (0,37,90):
            from shapely.ops import substring
            expected=rotate(substring(arc,2,arc.length-2),angle,origin=(0,0));region=rotate(shape,angle,origin=(0,0))
            paths,_=plan_paths([list(region.exterior.coords)],'centerline',resolution=.1)
            self.assertEqual(len(paths),1)
            actual=LineString(paths[0])
            self.assertLess(actual.hausdorff_distance(expected),.2)
            for tip in (expected.coords[0],expected.coords[-1]):
                self.assertLess(min(math.dist(tip,p) for p in (paths[0][0],paths[0][-1])),.1)

    def test_equal_distance_cache_is_immutable_to_callers(self):
        from welding import center_paths,_cached_center_paths
        region=box(0,0,30,4)
        _cached_center_paths.cache_clear()
        first,notes=center_paths(region,.2)
        saved=[list(p) for p in first]
        first[0].append((999,999));notes.append('caller mutation')
        second,new_notes=center_paths(region,.2)
        self.assertEqual(second,saved);self.assertNotIn('caller mutation',new_notes)
        self.assertEqual(_cached_center_paths.cache_info().hits,1)

    def test_connected_centerline_loop_and_tail_use_one_unrepeated_pass(self):
        from shapely.ops import unary_union
        paths=[[(0,0),(10,0),(10,10),(0,10),(0,0)],[(-5,0),(0,0),(0,-5)]]
        result=connected_weld_trails(paths)
        self.assertEqual(len(result),1)
        expected=unary_union([LineString(p) for p in paths]);actual=LineString(result[0])
        self.assertAlmostEqual(actual.length,expected.length)
        self.assertLess(actual.hausdorff_distance(expected),1e-8)

    def test_connected_centerline_does_not_cross_even_a_small_gap(self):
        paths=[[(0,0),(10,0)],[(10.0001,0),(20,0)]]
        self.assertEqual(len(connected_weld_trails(paths)),2)
        tee=[[(-10,0),(0,0),(10,0)],[(0,-10),(0,0)]]
        self.assertEqual(len(connected_weld_trails(tee)),2)

    def test_polygonal_n_keeps_both_long_stems_and_diagonal_straight(self):
        from shapely.ops import unary_union
        shape=unary_union([box(0,0,4,40),box(26,0,30,40),LineString([(2,38),(28,2)]).buffer(2,cap_style=2)])
        paths,_=plan_paths([list(shape.exterior.coords)],'centerline',resolution=.2)
        for x,lo,hi in ((2,2.1,36),(28,4,37.9)):
            expected=LineString([(x,lo),(x,hi)])
            from shapely.ops import unary_union
            self.assertLess(expected.difference(unary_union([LineString(p) for p in paths]).buffer(.02)).length,.01)
        self.assertTrue(any(math.dist(a,b)>43 for p in paths for a,b in zip(p,p[1:])))

    def test_simplification_keeps_shared_junctions_and_a_bowl_closed(self):
        region=box(-5,-12,25,15).difference(box(1,1,9,9))
        paths=[[(0,0),(.01,5),(0,10),(10,10),(10,0)],[(0,0),(10,0)],
               [(-.01,-10),(0,0)],[(10,0),(20,-10)]]
        result=straight_priority_trails(paths,region,.2,.5)
        self.assertTrue(centerline_encloses_holes(result,region))
        for node in ((0,0),(10,0)):
            self.assertTrue(any(node in p for p in result))

    def test_rounded_rectangle_ring_retains_its_rounded_medial_loop(self):
        outer=box(20,20,80,120).buffer(20,quad_segs=40)
        shape=outer.difference(outer.buffer(-12))
        expected=outer.buffer(-6).exterior
        for angle in (0,37,90):
            region=translate(rotate(shape,angle,origin=(0,0)),400,-200)
            target=translate(rotate(expected,angle,origin=(0,0)),400,-200)
            for resolution in (.1,.4):
                with self.subTest(angle=angle,resolution=resolution):
                    raw=[list(region.exterior.coords),list(region.interiors[0].coords)]
                    paths,_=plan_paths(raw,'centerline',resolution=resolution)
                    self.assertEqual(len(paths),1)
                    line=LineString(paths[0])
                    self.assertTrue(line.is_ring)
                    self.assertLess(line.hausdorff_distance(target),resolution*2)

    def test_genuinely_rounded_open_bend_is_not_changed_into_a_sharp_elbow(self):
        import math
        arc=[(22+8*math.cos(t),8+8*math.sin(t)) for t in [(-math.pi/2)+i*math.pi/256 for i in range(129)]]
        original=LineString([(0,0),*arc,(30,40)])
        shape=original.buffer(4,cap_style=2,quad_segs=40)
        from shapely.ops import substring
        expected=substring(original,4,original.length-4)
        for angle in (0,33):
            region=rotate(shape,angle,origin=(0,0))
            target=rotate(expected,angle,origin=(0,0))
            paths,_=plan_paths([list(region.exterior.coords)],'centerline',resolution=.2)
            self.assertEqual(len(paths),1)
            self.assertLess(LineString(paths[0]).hausdorff_distance(target),.4)

    def test_closed_arc_roundoff_snaps_only_the_closing_vertex(self):
        # An arc reaches slightly past its start on the next edge. Implicit
        # polygon closure would add a microscopic, self-touching return spike.
        raw=[(10,0),(10,30),(0,30),(0,0),(10,1e-14)]
        self.assertFalse(Polygon(raw).is_valid)
        region,_=solid_region([raw])
        self.assertTrue(region.is_valid);self.assertAlmostEqual(region.area,300)
        self.assertEqual(raw[-1],(10,1e-14))
        for mode in ('outline','fill','centerline'):
            self.assertTrue(plan_paths([raw],mode,width=1,resolution=.2)[0])
        with self.assertRaisesRegex(ValueError,'自交'):
            solid_region([[(0,0),(10,10),(0,10),(10,0),(0,0)]])

    def assert_single_ring_tail(self,shape,resolution,expected_ends=None):
        from shapely.ops import unary_union,polygonize
        raw=[list(shape.exterior.coords)]+[list(r.coords) for r in shape.interiors]
        paths,_=plan_paths(raw,'centerline',resolution=resolution,prune=.5)
        self.assertEqual(len(paths),1)
        line=LineString(paths[0]);geometry=unary_union([line])
        self.assertTrue(shape.buffer(1e-7).covers(line))
        self.assertAlmostEqual(line.length,geometry.length,places=6)
        faces=list(polygonize(geometry));self.assertEqual(len(faces),1)
        loop=faces[0].exterior
        self.assertTrue(faces[0].covers(Polygon(shape.interiors[0])))
        tail=paths[0]
        intersection=loop.intersection(geometry.difference(loop))
        self.assertEqual(intersection.geom_type,'Point')
        # Both inner and outer endpoints survive; the tail is not clipped to
        # the outer side of the ring or duplicated at its junction.
        self.assertGreater(Point(tail[0]).distance(Point(tail[-1])),20*resolution)
        if expected_ends:
            for end in expected_ends:
                self.assertLess(min(Point(end).distance(Point(p)) for p in (tail[0],tail[-1])),2*resolution)

    def test_ring_inner_and_outer_tail_have_exactly_one_junction(self):
        ring=Point(0,0).buffer(30,quad_segs=48).difference(Point(0,0).buffer(20,quad_segs=48))
        shape=ring.union(LineString([(12,-12),(40,-35)]).buffer(3,cap_style=2))
        for angle in (0,27,90):
            rotated=rotate(shape,angle,origin=(0,0))
            length=math.hypot(28,23)
            inset=((12+28/length*3,-12-23/length*3),(40-28/length*3,-35+23/length*3))
            ends=[tuple(rotate(Point(p),angle,origin=(0,0)).coords)[0] for p in inset]
            for resolution in (.1,.2,.4):
                with self.subTest(angle=angle,resolution=resolution):self.assert_single_ring_tail(rotated,resolution,ends)

    def test_actual_arial_q_preserves_inner_tail_and_single_intersection(self):
        from matplotlib.textpath import TextPath
        from matplotlib.font_manager import FontProperties,findfont
        font=FontProperties(family='Arial')
        try:findfont(font,fallback_to_default=False)
        except ValueError:self.skipTest('Arial is not installed')
        raw=[list(map(tuple,p)) for p in TextPath((0,0),'Q',size=200,prop=font).to_polygons()]
        shape,_=solid_region(raw)
        for angle in (0,37):
            for resolution in (.1,.4):
                self.assert_single_ring_tail(rotate(shape,angle,origin=(0,0)),resolution)

    def test_drawing1_long_legs_and_short_crossbars(self):
        sample = Path(__file__).resolve().parent.parent / 'CAD图纸' / 'Drawing1.dxf'
        if not sample.exists():
            self.skipTest('Drawing1 companion DXF is not available')
        from cad_reader import load_dxf
        import ezdxf
        texts = [e.plain_text() for e in ezdxf.readfile(str(sample)).modelspace() if e.dxftype() in ('TEXT','MTEXT')]
        if texts != ['AAA']:
            self.skipTest('Drawing1 has been edited; original AAA fixture no longer available')
        raw, _, _ = load_dxf(str(sample), 0.05, 1)
        region, _ = solid_region(raw)
        paths, _ = plan_paths(raw, 'centerline')
        self.assertEqual(sorted(map(len, paths)), [2,2,2,4,4,4])
        self.assertTrue(all(region.buffer(1e-7).covers(LineString(p)) for p in paths))
        for path in paths:
            if len(path)==4:
                # Each leg is one straight segment across the crossbar junction.
                self.assertGreater(abs(path[0][1]-path[1][1]), 100)
                self.assertGreater(abs(path[2][1]-path[3][1]), 100)

    def test_long_primary_stroke_remains_straight_across_junction(self):
        tee = box(10,0,14,24).union(box(0,20,24,24))
        for angle in (0, 33, 90):
            shape = rotate(tee, angle, origin=(0,0))
            paths, _ = plan_paths([list(shape.exterior.coords)], 'centerline')
            primary = rotate(LineString([(2,22),(22,22)]), angle, origin=(0,0))
            secondary = rotate(LineString([(12,2),(12,22)]), angle, origin=(0,0))
            self.assertEqual(len(paths), 2)
            # Contracted endpoints are boundary-sampling collision estimates.
            self.assertLess(min(LineString(p).hausdorff_distance(primary) for p in paths), .05)
            self.assertLess(min(LineString(p).hausdorff_distance(secondary) for p in paths), .05)
            # Keep shared junction vertices without bending the long stroke or
            # welding it twice; export discretizes this straight run anyway.
            self.assertLess(min(abs(LineString(p).length-primary.length) for p in paths),.1)

    def test_bend_uses_intersection_of_long_straight_supports(self):
        elbow = box(0,0,4,24).union(box(0,0,24,4))
        paths, _ = plan_paths([list(elbow.exterior.coords)], 'centerline')
        expected = LineString([(2,22),(2,2),(22,2)])
        self.assertEqual(len(paths), 1)
        self.assertLess(LineString(paths[0]).hausdorff_distance(expected), 1e-6)
        self.assertEqual(len(paths[0]), 3)

    def test_edge_midline_bar_contracts_all_caps_by_its_half_width(self):
        for angle in (0, 27, 90):
            bar = rotate(box(0, 0, 30, 4), angle, origin=(0,0))
            paths, _ = plan_paths([list(bar.exterior.coords)], 'centerline')
            self.assertEqual(len(paths), 1)
            actual = LineString(paths[0])
            expected = rotate(LineString([(2,2),(28,2)]), angle, origin=(0,0))
            self.assertLess(actual.hausdorff_distance(expected), .02)
            self.assertEqual(len(paths[0]), 2)

    def test_edge_midlines_connect_bends_and_junctions(self):
        elbow = box(0,0,4,24).union(box(0,0,24,4))
        tee = box(10,0,14,24).union(box(0,20,24,24))
        for shape, count in ((elbow,1), (tee,2)):
            paths, _ = plan_paths([list(shape.exterior.coords)], 'centerline')
            self.assertEqual(len(paths), count)
            self.assertTrue(all(shape.buffer(1e-7).covers(LineString(p)) for p in paths))
            self.assertGreaterEqual(sum(LineString(p).length for p in paths), 39.9)

    def test_compact_solids_blocked_only_for_centerline(self):
        disk = Point(0, 0).buffer(10, quad_segs=64)
        shapes = [disk, rotate(scale(disk, 1.5, 1), 37),
                  Polygon([(0,0),(10,0),(10,10),(0,10)])]
        for shape in shapes:
            boundary = list(shape.exterior.coords)
            with self.assertRaisesRegex(ValueError, '中心线模式不适用'):
                plan_paths([boundary], 'centerline')
            for mode in ('fill', 'outline'):
                self.assertTrue(plan_paths([boundary], mode)[0])

    def test_mixed_drawing_is_rejected_instead_of_skipping_disk(self):
        bar = [(0,0),(30,0),(30,4),(0,4),(0,0)]
        disk = list(Point(50, 20).buffer(10).exterior.coords)
        with self.assertRaisesRegex(ValueError, '已停止本次轨迹生成'):
            plan_paths([bar, disk], 'centerline')

    def test_round_ring_and_rotated_bar_allowed(self):
        ring = [list(Point(0, 0).buffer(r, quad_segs=64).exterior.coords) for r in (10, 8)]
        self.assertTrue(plan_paths(ring, 'centerline')[0])
        bar = rotate(Polygon([(0,0),(30,0),(30,4),(0,4)]), 45)
        self.assertTrue(plan_paths([list(bar.exterior.coords)], 'centerline')[0])

    def test_outline_includes_holes(self):
        paths, _ = plan_paths([OUTER, HOLE, OUTER], 'outline')
        self.assertEqual(len(paths), 2)
        self.assertEqual(sorted(Polygon(p).area for p in paths), [100, 600])

    def test_fill_respects_hole_and_width(self):
        paths, _ = plan_paths([OUTER, HOLE], 'fill', width=2, overlap=25, angle=30)
        region, _ = solid_region([OUTER, HOLE])
        self.assertGreater(len(paths), 5)
        for path in paths:
            self.assertTrue(region.buffer(1e-7).covers(LineString(path).buffer(0.999)))

    def test_skeleton_single_bar_and_cycle(self):
        bar = [(0,0),(30,0),(30,4),(0,4),(0,0)]
        paths, _ = plan_paths([bar], 'centerline', resolution=0.2)
        self.assertEqual(len(paths), 1)
        self.assertGreater(LineString(paths[0]).length, 25)
        paths, _ = plan_paths([OUTER, HOLE], 'centerline', resolution=0.2)
        region, _ = solid_region([OUTER, HOLE])
        self.assertTrue(paths)
        self.assertTrue(all(region.covers(LineString(p)) for p in paths))

    def test_four_fill_directions_and_continuity(self):
        for direction in FILL_MODES:
            separate, _ = plan_paths([OUTER], 'fill', direction=direction)
            connected, _ = plan_paths([OUTER], 'fill', direction=direction, continuous=True)
            self.assertLess(len(connected), len(separate))
            self.assertTrue(all(Polygon(OUTER).covers(LineString(p)) for p in connected))
        down, _ = plan_paths([OUTER], 'fill', direction='从上向下')
        self.assertGreater(down[0][0][1], down[1][0][1])
        right, _ = plan_paths([OUTER], 'fill', direction='从左向右')
        self.assertLess(right[0][0][0], right[1][0][0])
        inward, _ = plan_paths([OUTER], 'fill', direction='由外向内')
        outward, _ = plan_paths([OUTER], 'fill', direction='由内向外')
        self.assertGreater(Polygon(inward[0]).area, Polygon(inward[-1]).area)
        self.assertLess(Polygon(outward[0]).area, Polygon(outward[-1]).area)

    def test_continuous_fill_never_crosses_hole(self):
        region, _ = solid_region([OUTER, HOLE])
        for direction in FILL_MODES:
            paths, _ = plan_paths([OUTER, HOLE], 'fill', direction=direction, continuous=True)
            self.assertTrue(all(region.buffer(1e-7).covers(LineString(p).buffer(0.999)) for p in paths))

    def test_minimum_center_trails_without_repeated_edges(self):
        # Four odd vertices: minimum is two trails, not four branches.
        branches = [[(0,0),p] for p in [(10,0),(-10,0),(0,10),(0,-10)]]
        trails = minimum_trails(branches, Polygon([(-20,-20),(20,-20),(20,20),(-20,20)]), 0, 0)
        self.assertEqual(len(trails), 2)
        self.assertAlmostEqual(sum(LineString(p).length for p in trails), 40)
        # An attached loop and tail admit one trail, without duplicate welding.
        branches = [[(0,0),(5,0),(5,5),(0,5),(0,0)], [(0,0),(-5,0)]]
        trails = minimum_trails(branches, Polygon([(-20,-20),(20,-20),(20,20),(-20,20)]), 0, 0)
        self.assertEqual(len(trails), 1)
        self.assertAlmostEqual(LineString(trails[0]).length, 25)

    def test_prune_spur_and_simplify_without_losing_main_stroke(self):
        region = Polygon([(-20,-20),(20,-20),(20,20),(-20,20)])
        branches = [[(-10,0),(-5,0.05),(0,0)], [(0,0),(5,0.05),(10,0)], [(0,0),(0,0.2)]]
        trails = minimum_trails(branches, region, 0.1, 0.5)
        self.assertEqual(len(trails), 1)
        self.assertEqual(len(trails[0]), 2)
        self.assertAlmostEqual(LineString(trails[0]).length, 20)
        self.assertEqual(len(minimum_trails(branches, region, 0, 0)), 2)

    def test_continuous_does_not_join_separate_islands(self):
        second = [(x+50,y) for x,y in OUTER]
        paths, _ = plan_paths([OUTER, second], 'fill', continuous=True)
        self.assertGreaterEqual(len(paths), 2)
        region, _ = solid_region([OUTER, second])
        self.assertTrue(all(region.covers(LineString(p)) for p in paths))

    def test_narrow_fill_and_open_geometry_rejected(self):
        with self.assertRaises(ValueError):
            plan_paths([[(0,0),(1,0)]], 'fill')
        with self.assertRaises(ValueError):
            plan_paths([OUTER], 'fill', width=100)
        with self.assertRaises(ValueError):
            plan_paths([OUTER], 'fill', overlap=100)

if __name__ == '__main__':
    unittest.main()
