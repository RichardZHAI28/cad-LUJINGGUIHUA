import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent/'.vendor'))
import math
import tempfile
import unittest

import ezdxf
from ezdxf.enums import TextEntityAlignment
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.textpath import TextPath
from geometry import transform
from cad_reader import load_dxf


def bounds(paths):
    points = [p for path in paths for p in path]
    return (min(x for x, y in points), min(y for x, y in points),
            max(x for x, y in points), max(y for x, y in points))


class TextPlacementTests(unittest.TestCase):
    def document(self, font='DejaVuSans.ttf'):
        doc = ezdxf.new()
        doc.header['$INSUNITS'] = 4
        doc.styles.get('Standard').dxf.font = font
        return doc

    def read(self, doc, scale=1):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'placement.dxf'
            doc.saveas(file)
            paths, warnings, _ = load_dxf(file, .1, scale)
        self.assertTrue(paths, warnings)
        self.assertFalse(any('失败' in w for w in warnings), warnings)
        return paths

    def assert_paths_close(self, actual, expected):
        self.assertEqual(list(map(len, actual)), list(map(len, expected)))
        for path, want in zip(actual, expected):
            for (x, y), (wx, wy) in zip(path, want):
                self.assertAlmostEqual(x, wx, places=7)
                self.assertAlmostEqual(y, wy, places=7)

    def test_mtext_top_anchor_200_mm_is_not_a_baseline(self):
        doc = self.document()
        doc.modelspace().add_mtext('X', dxfattribs={'insert': (0, 200), 'char_height': 200,
                                                   'attachment_point': 1})
        box = bounds(self.read(doc))
        self.assertAlmostEqual(box[1], 0)
        self.assertAlmostEqual(box[3], 200)

    def test_all_nine_mtext_anchors_use_the_same_insertion(self):
        prop = FontProperties(fname=findfont(FontProperties(family=['DejaVu Sans'])))
        # MTEXT aligns visible extents; TEXT uses baseline side bearings.
        glyph=TextPath((0,0),'X',size=100,prop=prop).get_extents()
        ink_width=glyph.width*20/glyph.height
        base = None
        for attachment in range(1, 10):
            with self.subTest(attachment=attachment):
                doc = self.document()
                doc.modelspace().add_mtext('X', dxfattribs={'insert': (57, 83), 'char_height': 20,
                                                           'width': 200, 'attachment_point': attachment})
                paths = self.read(doc)
                if base is None:
                    base = paths
                row, column = divmod(attachment-1, 3)
                expected = [[(x-column*ink_width/2, y+row*10) for x, y in p] for p in base]
                self.assert_paths_close(paths, expected)
                box = bounds(paths)
                self.assertAlmostEqual(box[1], 63+row*10)
                self.assertAlmostEqual(box[3], 83+row*10)

    def test_multiline_spacing_is_five_thirds_of_cap_height(self):
        for factor in (1, 1.5):
            with self.subTest(factor=factor):
                doc = self.document()
                doc.modelspace().add_mtext('X\\PX', dxfattribs={'insert': (0, 80), 'char_height': 20,
                                                               'line_spacing_factor': factor})
                paths = self.read(doc)
                self.assertEqual(len(paths), 2)
                self.assertAlmostEqual(bounds(paths[:1])[1], 60)
                self.assertAlmostEqual(bounds(paths[1:])[1], 60-20*5/3*factor)

    def test_wrap_only_at_word_boundaries_and_honor_width(self):
        doc = self.document()
        entity = doc.modelspace().add_mtext('X X X', dxfattribs={'insert': (0, 80), 'char_height': 20,
                                                                'width': 30})
        paths = self.read(doc)
        self.assertEqual(len(paths), 3)
        for row, path in enumerate(paths):
            self.assertAlmostEqual(bounds([path])[1], 60-row*20*5/3)
        entity.text = 'XXX'
        paths = self.read(doc)
        self.assertGreater(bounds(paths)[2], 30)
        self.assertAlmostEqual(bounds(paths)[1], 60)

    def test_text_top_uses_alignment_point_not_obsolete_insert(self):
        doc = self.document()
        entity = doc.modelspace().add_text('X', dxfattribs={'height': 200})
        entity.set_placement((40, 200), align=TextEntityAlignment.TOP_LEFT)
        entity.dxf.insert = (990, 995)
        paths = self.read(doc)
        self.assertAlmostEqual(bounds(paths)[1], 0)
        self.assertAlmostEqual(bounds(paths)[3], 200)
        baseline_doc = self.document()
        baseline_doc.modelspace().add_text('X', dxfattribs={'insert': (40, 0), 'height': 200})
        self.assert_paths_close(paths, self.read(baseline_doc))

    def test_text_bottom_aligns_descender_to_alignment_point(self):
        doc = self.document()
        entity = doc.modelspace().add_text('p', dxfattribs={'height': 200})
        entity.set_placement((40, 83), align=TextEntityAlignment.BOTTOM_LEFT)
        self.assertAlmostEqual(bounds(self.read(doc))[1], 83)

    def test_rotation_is_applied_after_attachment_offset(self):
        for kind in ('TEXT', 'MTEXT'):
            doc = self.document()
            if kind == 'MTEXT':
                entity = doc.modelspace().add_mtext('X', dxfattribs={'insert': (57, 83), 'char_height': 20})
            else:
                entity = doc.modelspace().add_text('X', dxfattribs={'height': 20})
                entity.set_placement((57, 83), align=TextEntityAlignment.TOP_LEFT)
            base = self.read(doc)
            for angle in (90, 37, -135):
                with self.subTest(kind=kind, angle=angle):
                    entity.dxf.rotation = angle
                    r = math.radians(angle)
                    expected = [[(57+(x-57)*math.cos(r)-(y-83)*math.sin(r),
                                  83+(x-57)*math.sin(r)+(y-83)*math.cos(r)) for x, y in p] for p in base]
                    self.assert_paths_close(self.read(doc), expected)

    def test_mtext_direction_vector_precedes_rotation(self):
        doc = self.document()
        entity = doc.modelspace().add_mtext('X', dxfattribs={'insert': (57, 83), 'char_height': 20})
        base = self.read(doc)
        entity.dxf.rotation = 37
        entity.dxf.text_direction = (0, 1, 0)
        self.assert_paths_close(self.read(doc), [[(57-(y-83), 83+(x-57)) for x, y in p] for p in base])

    def test_font_scale_keeps_the_attachment_fixed_and_preserves_line_breaks(self):
        doc = self.document()
        doc.modelspace().add_mtext('X X', dxfattribs={'insert': (57, 83), 'char_height': 20, 'width': 30})
        base = self.read(doc)
        scaled = self.read(doc, 1.1)
        self.assert_paths_close(scaled, [[(57+(x-57)*1.1, 83+(y-83)*1.1) for x, y in p] for p in base])

    def test_inline_height_and_width_are_not_lost(self):
        doc = self.document()
        entity = doc.modelspace().add_mtext('X', dxfattribs={'insert': (0, 200), 'char_height': 200})
        box = bounds(self.read(doc))
        entity.text = r'\H0.5x;\W2;X'
        smaller = bounds(self.read(doc))
        self.assertAlmostEqual(smaller[3], 200)
        self.assertAlmostEqual(smaller[1], 100)
        self.assertAlmostEqual(smaller[2]-smaller[0], box[2]-box[0])

    def test_text_ocs_and_mtext_extrusion_are_projected_after_layout(self):
        for kind in ('TEXT', 'MTEXT'):
            with self.subTest(kind=kind):
                doc = self.document()
                if kind == 'MTEXT':
                    entity = doc.modelspace().add_mtext('X', dxfattribs={'insert': (0, 200), 'char_height': 200})
                else:
                    entity = doc.modelspace().add_text('X', dxfattribs={'height': 200})
                    entity.set_placement((0, 200), align=TextEntityAlignment.TOP_LEFT)
                base = self.read(doc)
                entity.dxf.extrusion = (0, 0, -1)
                expected = ([[(x, 400-y) for x, y in p] for p in base] if kind == 'MTEXT'
                            else [[(-x, y) for x, y in p] for p in base])
                self.assert_paths_close(self.read(doc), expected)

    def test_block_translation_and_user_origin_are_each_applied_once(self):
        doc = self.document()
        block = doc.blocks.new('letters')
        block.add_mtext('X', dxfattribs={'insert': (0, 200), 'char_height': 200})
        doc.modelspace().add_blockref('letters', (300, 400))
        paths = self.read(doc)
        self.assertAlmostEqual(bounds(paths)[1], 400)
        self.assertAlmostEqual(bounds(paths)[3], 600)
        converted = [[transform(p, (300, 400), 0, 1) for p in path] for path in paths]
        self.assertAlmostEqual(bounds(converted)[1], 0)
        self.assertAlmostEqual(bounds(converted)[3], 200)

    def test_cap_height_and_anchor_across_installed_font_families(self):
        for family in ('Arial', 'Times New Roman', 'Courier New', 'Microsoft YaHei',
                       'SimSun', 'SimHei', 'KaiTi', 'FangSong', 'DejaVu Sans'):
            with self.subTest(family=family):
                try:
                    file = findfont(FontProperties(family=[family]), fallback_to_default=False)
                except ValueError:
                    continue
                doc = self.document(Path(file).name)
                entity = doc.modelspace().add_mtext('X', dxfattribs={'insert': (11, 237), 'char_height': 200})
                top = self.read(doc)
                self.assertAlmostEqual(bounds(top)[1], 37)
                self.assertAlmostEqual(bounds(top)[3], 237)
                doc.modelspace().delete_entity(entity)
                doc.modelspace().add_text('X', dxfattribs={'insert': (11, 37), 'height': 200})
                baseline=self.read(doc)
                bearing=max(0,bounds(baseline)[0]-11)
                self.assert_paths_close([[(x-bearing,y) for x,y in p] for p in baseline],top)

    def test_round_letters_match_recorded_autocad_2016_extents(self):
        # Independent reference: bounds read from AutoCAD 2016 via ActiveX,
        # not calculated by this importer (diagnostic native-oracle.json).
        try:
            file=findfont(FontProperties(family=['Arial']),fallback_to_default=False)
        except ValueError:
            self.skipTest('Arial is not installed')
        references={
            'ABCD':((293.1787175989086,500),(396.5893587994543,603.4106412005457),
                    (500,706.8212824010914)),
            'Q':((280.9004092769441,500),(390.450204638472,609.549795361528),
                 (500,719.099590723056)),
            'ABCD\\PQp':((-95.8162801273307,500),(202.091859936335,797.908140063665),
                          (500,1095.81628012733))}
        for text,rows in references.items():
            for row,(minimum,maximum) in enumerate(rows):
                with self.subTest(text=text,row=row):
                    doc=self.document(Path(file).name)
                    doc.modelspace().add_mtext(text,dxfattribs={'insert':(0,500),'char_height':200,
                                                               'width':1500,'attachment_point':row*3+1})
                    box=bounds(self.read(doc))
                    self.assertAlmostEqual(box[1],minimum,delta=.05)
                    self.assertAlmostEqual(box[3],maximum,delta=.05)

    def test_leading_blank_paragraph_is_preserved(self):
        try:
            file=findfont(FontProperties(family=['Arial']),fallback_to_default=False)
        except ValueError:
            self.skipTest('Arial is not installed')
        doc=self.document(Path(file).name)
        doc.modelspace().add_mtext('\\PABCD',dxfattribs={'insert':(0,500),'char_height':200})
        paths=self.read(doc)
        # AutoCAD's exploded TEXT baseline for the second paragraph.
        self.assertAlmostEqual(bounds(paths[:1])[1],-36.7439745338791,delta=.02)

    def test_72_recorded_native_cad_layouts(self):
        import json
        from cad_reader import cad_font
        from cad_text import text_outlines
        from shapely.geometry import MultiLineString
        try:
            file=findfont(FontProperties(family=['Arial']),fallback_to_default=False)
        except ValueError:
            self.skipTest('Arial is not installed')
        fixture=json.loads((Path(__file__).parent/'test_data'/'native_mtext.json').read_text(encoding='utf-8'))
        for case in fixture['cases']:
            with self.subTest(text=case['text'],attachment=case['attachment']):
                doc=self.document(Path(file).name)
                entity=doc.modelspace().add_mtext(case['text'],dxfattribs={'insert':(0,500),
                     'char_height':200,'width':1500,'attachment_point':case['attachment']})
                font,_=cad_font(doc,entity)
                expected=[]
                for chunk in case['native_text']:
                    native=doc.modelspace().add_text(chunk['text'],dxfattribs={
                        'insert':chunk['insert'],'height':chunk['height'],'width':chunk['width']})
                    expected.extend(text_outlines(native,font,1))
                distance=MultiLineString(text_outlines(entity,font,1)).hausdorff_distance(MultiLineString(expected))
                self.assertLess(distance,.1)


if __name__ == '__main__':
    unittest.main()
