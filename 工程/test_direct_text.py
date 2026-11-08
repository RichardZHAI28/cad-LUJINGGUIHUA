import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.vendor'))
import unittest
import tempfile
from unittest.mock import patch
from matplotlib import font_manager
from direct_text import TextSpec,text_boundaries,available_fonts
from font_support import CadFontError
from welding import solid_region,plan_paths,centerline_encloses_holes
from shapely.geometry import LineString
from cad_reader import load_dxf
import ezdxf


def bounds(paths):
    return solid_region(paths)[0].bounds


class DirectTextTests(unittest.TestCase):
    def setUp(self):
        self.font=font_manager.findfont(font_manager.FontProperties(family=['DejaVu Sans']),fallback_to_default=False)

    def test_literal_multiline_size_anchor_and_three_modes(self):
        spec=TextSpec(text='ABQ\n012',font_file=self.font,height=20,x=12,y=-8)
        raw=text_boundaries(spec)
        region,_=solid_region(raw)
        self.assertAlmostEqual(region.bounds[0],12);self.assertAlmostEqual(region.bounds[1],-8)
        enlarged=text_boundaries(spec,1.2)
        self.assertAlmostEqual(bounds(enlarged)[2]-12,(region.bounds[2]-12)*1.2)
        self.assertAlmostEqual(bounds(enlarged)[3]+8,(region.bounds[3]+8)*1.2)
        for mode in ('outline','fill','centerline'):
            paths,_=plan_paths(raw,mode,width=1,resolution=.25)
            self.assertTrue(paths)
        self.assertGreater(sum(len(p.interiors) for p in region.geoms),0) if hasattr(region,'geoms') else self.assertGreater(len(region.interiors),0)

    def test_missing_font_glyph_or_empty_input_never_silently_substitutes(self):
        for spec in (TextSpec(font_file='missing.ttf'),TextSpec(text='测试',font_file=self.font)):
            with self.assertRaises(CadFontError):text_boundaries(spec)
        with self.assertRaises(ValueError):text_boundaries(TextSpec(text=' \n\t',font_file=self.font))

    def test_ziti_fonts_are_discovered_and_use_their_actual_capitals(self):
        fonts=available_fonts()
        for name,text in [('ZITI1','NO SMOKING 0123456789'),('ZITI2','ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789')]:
            file=next((f for label,f in fonts.items() if Path(f).name.casefold()==name.lower()+'.ttf'),None)
            if file is None:self.skipTest(name+' is not installed')
            with self.subTest(font=name):
                raw=text_boundaries(TextSpec(text=text,font_file=file,height=30))
                self.assertGreater(solid_region(raw)[0].area,0)
                glyph=text_boundaries(TextSpec(text='N',font_file=file,height=30))
                self.assertAlmostEqual(bounds(glyph)[3],30,places=6)
                if name=='ZITI1':
                    with self.assertRaises(CadFontError):text_boundaries(TextSpec(text='A',font_file=file))
                doc=ezdxf.new();doc.styles.get('Standard').dxf.font=name+'.ttf'
                doc.modelspace().add_text('NO',dxfattribs={'height':30})
                with tempfile.TemporaryDirectory() as folder:
                    path=Path(folder)/'font.dxf';doc.saveas(path)
                    self.assertTrue(load_dxf(path,.1,1)[0])

    def test_actual_ziti_o_keeps_a_balanced_rounded_loop_at_small_and_large_sizes(self):
        fonts=available_fonts()
        for name in ('ZITI1','ZITI2'):
            file=next((f for f in fonts.values() if Path(f).name.lower()==name.lower()+'.ttf'),None)
            if file is None:self.skipTest(name+' is not installed')
            for height in (30,400):
                with self.subTest(font=name,height=height):
                    raw=text_boundaries(TextSpec(text='O',font_file=file,height=height))
                    region,_=solid_region(raw)
                    paths,_=plan_paths(raw,'centerline',resolution=.2)
                    self.assertEqual(len(paths),1)
                    line=LineString(paths[0]);self.assertTrue(line.is_ring)
                    imbalance=max(abs(region.exterior.distance(p)-region.interiors[0].distance(p))
                                  for p in (line.interpolate(i/500,normalized=True) for i in range(500)))
                    self.assertLess(imbalance,.6)

    def test_r_bowls_are_not_removed_by_distant_straight_supports(self):
        for name in ('DejaVu Sans','Arial','Verdana','SimHei'):
            try:file=font_manager.findfont(font_manager.FontProperties(family=[name]),fallback_to_default=False)
            except ValueError:continue
            with self.subTest(font=name):
                raw=text_boundaries(TextSpec(text='R',font_file=file,height=40))
                region,_=solid_region(raw)
                self.assertEqual(len(region.interiors),1)
                paths,_=plan_paths(raw,'centerline',resolution=.2)
                self.assertTrue(centerline_encloses_holes(paths,region))

    def test_ziti_cap_offset_collisions_precede_straight_intersections(self):
        fonts=available_fonts()
        for name in ('ZITI1','ZITI2'):
            file=next((f for f in fonts.values() if Path(f).name.lower()==name.lower()+'.ttf'),None)
            if file is None:self.skipTest(name+' is not installed')
            for glyph in 'MKN':
                with self.subTest(font=name,glyph=glyph):
                    raw=text_boundaries(TextSpec(text=glyph,font_file=file,height=400))
                    region,_=solid_region(raw)
                    paths,_=plan_paths(raw,'centerline',resolution=.2)
                    xy=[p for path in paths for p in path]
                    self.assertTrue(all(region.buffer(1e-7).covers(LineString(p)) for p in paths))
                    if glyph in 'MN':
                        self.assertGreater(min(p[1] for p in xy)-region.bounds[1],20)
                        self.assertGreater(region.bounds[3]-max(p[1] for p in xy),20)
                        # The end and side fronts of the 80 mm stem meet
                        # at d=40. A dominant slant may not displace this event.
                        self.assertTrue(any(abs(p[0]-40)<.1 and abs(p[1]-360)<.1 for p in xy))
                    else:
                        self.assertGreater(min(p[1] for p in xy)-region.bounds[1],20)
                        self.assertGreater(region.bounds[3]-max(p[1] for p in xy),20)

    def test_ziti_a_keeps_both_feet_crossbar_and_hole(self):
        file=next((f for f in available_fonts().values() if Path(f).name.lower()=='ziti2.ttf'),None)
        if file is None:self.skipTest('ZITI2 is not installed')
        raw=text_boundaries(TextSpec(text='A',font_file=file,height=400))
        region,_=solid_region(raw);paths,_=plan_paths(raw,'centerline',resolution=.2)
        self.assertTrue(centerline_encloses_holes(paths,region))
        self.assertEqual(len(paths),2)
        ends=[p for path in paths for p in (path[0],path[-1])]
        self.assertEqual(sum(p[1]<60 for p in ends),2)
        self.assertGreater(region.bounds[3]-max(p[1] for path in paths for p in path),20)

    def test_straight_priority_does_not_square_ziti_g_lower_rounding(self):
        file=next((f for f in available_fonts().values() if Path(f).name.lower()=='ziti1.ttf'),None)
        if file is None:self.skipTest('ZITI1 is not installed')
        raw=text_boundaries(TextSpec(text='G',font_file=file,height=400))
        region,_=solid_region(raw);paths,_=plan_paths(raw,'centerline',resolution=.2)
        from shapely.geometry import Point
        corner=Point(region.bounds[0]+40,region.bounds[1]+40)
        self.assertGreater(min(LineString(p).distance(corner) for p in paths),5)

    def test_offset_events_are_rotation_and_scale_invariant(self):
        file=next((f for f in available_fonts().values() if Path(f).name.lower()=='ziti2.ttf'),None)
        if file is None:self.skipTest('ZITI2 is not installed')
        from welding import offset_collision_paths
        from shapely.affinity import rotate,scale
        from shapely.ops import unary_union
        for glyph in 'AMN':
            region,_=solid_region(text_boundaries(TextSpec(text=glyph,font_file=file,height=400)))
            base=unary_union([LineString(p) for p in offset_collision_paths(region,.2)])
            for angle,factor in ((27,1),(90,.075)):
                with self.subTest(glyph=glyph,angle=angle,factor=factor):
                    shape=rotate(scale(region,xfact=factor,yfact=factor,origin=(0,0)),angle,origin=(0,0))
                    actual=unary_union([LineString(p) for p in offset_collision_paths(shape,.2)])
                    expected=rotate(scale(base,xfact=factor,yfact=factor,origin=(0,0)),angle,origin=(0,0))
                    self.assertLess(actual.hausdorff_distance(expected),1e-5)


if __name__=='__main__':unittest.main()
