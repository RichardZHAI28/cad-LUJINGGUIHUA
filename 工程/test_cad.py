import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '.vendor'))
import tempfile
import unittest
from pathlib import Path
import ezdxf
from cad_reader import load_dxf

class CadTests(unittest.TestCase):
    def test_solid_hatch_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / 'hatch.dxf')
            doc = ezdxf.new()
            hatch = doc.modelspace().add_hatch()
            hatch.paths.add_polyline_path([(0,0),(30,0),(30,20),(0,20)], is_closed=True)
            hatch.paths.add_polyline_path([(10,5),(20,5),(20,15),(10,15)], is_closed=True)
            doc.saveas(filename)
            paths, warnings, _ = load_dxf(filename, 0.1, 1)
            self.assertEqual(len(paths), 2)
            self.assertFalse(warnings)
            from welding import solid_region
            region, _ = solid_region(paths)
            self.assertAlmostEqual(region.area, 500)

    def test_geometry_text_and_font_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / 'test.dxf')
            doc = ezdxf.new()
            model = doc.modelspace()
            doc.styles.get('Standard').dxf.font='DejaVuSans.ttf'
            model.add_line((0, 0), (10, 0))
            model.add_circle((20, 20), radius=5)
            model.add_text('O', dxfattribs={'insert': (40, 0), 'height': 10})
            model.add_mtext('AB\\PCD', dxfattribs={'insert': (60, 0), 'char_height': 5})
            doc.saveas(filename)
            paths, warnings, _ = load_dxf(filename, 0.1, 1)
            self.assertGreaterEqual(len(paths), 5)
            self.assertFalse(any('失败' in warning for warning in warnings), warnings)
            large, _, _ = load_dxf(filename, 0.1, 1.1)
            self.assertEqual(paths[:2], large[:2])
            self.assertGreater(max(x for x, y in large[2]), max(x for x, y in paths[2]))

    def test_requested_font_is_used_without_silent_substitution(self):
        from cad_reader import cad_font
        from matplotlib.font_manager import FontProperties,findfont
        from matplotlib.textpath import TextPath
        doc=ezdxf.new();doc.styles.get('Standard').dxf.font='DejaVuSans.ttf'
        entity=doc.modelspace().add_mtext('Q',dxfattribs={'char_height':100})
        font,name=cad_font(doc,entity)
        self.assertEqual(Path(font.get_file()).name.lower(),'dejavusans.ttf')
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'q.dxf';doc.saveas(file)
            paths,warnings,_=load_dxf(file,.1,1)
            cap=TextPath((0,0),'X',size=100,prop=font).get_extents().height
            size=10000/cap
            box=TextPath((0,0),'Q',size=size,prop=font).get_extents()
            top=max(100,box.ymax)
            expected=TextPath((-max(0,box.xmin),-top),'Q',size=size,prop=font).to_polygons()
            self.assertEqual(len(paths),len(expected))
            for actual,want in zip(paths,expected):
                self.assertEqual(len(actual),len(want))
                for (x,y),(wx,wy) in zip(actual,want):
                    self.assertAlmostEqual(x,wx,places=7)
                    self.assertAlmostEqual(y,wy,places=7)
        doc.styles.get('Standard').dxf.font='missing_cad_font_8723.ttf'
        with self.assertRaisesRegex(ValueError,'缺少 CAD 字体'):cad_font(doc,entity)
        doc.styles.get('Standard').dxf.font='txt.shx'
        with self.assertRaisesRegex(ValueError,'SHX'):cad_font(doc,entity)
        entity.text=r'\fDejaVu Sans|b1|i0;Q'
        font,_=cad_font(doc,entity)
        self.assertIn('bold',Path(font.get_file()).name.lower())

if __name__ == '__main__':
    unittest.main()

