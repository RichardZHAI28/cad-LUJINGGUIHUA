"""Regression checks for hidden CAD content and WCS-only drawing import."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.vendor'))
import tempfile
import unittest
from unittest.mock import patch

import ezdxf
from ezdxf.math import UCS
from shapely.geometry import MultiLineString
from cad_reader import load_dxf
from geometry import transform
from welding import solid_region,plan_paths


def rectangle(space,x=0,layer='0'):
    return space.add_lwpolyline([(x,0),(x+20,0),(x+20,10),(x,10)],close=True,
                                dxfattribs={'layer':layer})


def bounds(paths):
    points=[v for path in paths for v in path]
    return (min(x for x,y in points),min(y for x,y in points),
            max(x for x,y in points),max(y for x,y in points))


class ImportTests(unittest.TestCase):
    def read(self,doc,system='wcs'):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'fixture.dxf';doc.saveas(file)
            return load_dxf(file,.01,1,coordinate_system=system)

    def test_frozen_block_hides_explicit_child_layers_and_fonts(self):
        doc=ezdxf.new();doc.layers.new('frozen').freeze();doc.layers.new('visible')
        block=doc.blocks.new('background')
        rectangle(block,100,'visible')
        doc.styles.get('Standard').dxf.font='missing_hidden_font.shx'
        block.add_mtext('Not a weld',dxfattribs={'layer':'visible'})
        doc.modelspace().add_blockref('background',(0,0),dxfattribs={'layer':'frozen'})
        rectangle(doc.modelspace())
        paths,notes,_=self.read(doc)
        self.assertEqual(len(paths),1)
        self.assertEqual(bounds(paths),(0,0,20,10))
        self.assertTrue(any('frozen' in note for note in notes))
        self.assertEqual(solid_region(paths)[0].area,200)

    def test_off_layers_and_invisible_entities_are_hidden_but_locked_and_nonplot_are_visible(self):
        doc=ezdxf.new();space=doc.modelspace()
        doc.layers.new('off').off();doc.layers.new('locked').lock()
        doc.layers.new('nonplot',dxfattribs={'plot':0})
        rectangle(space,100,'off')
        hidden=rectangle(space,200);hidden.dxf.invisible=1
        rectangle(space,300,'locked');rectangle(space,400,'nonplot')
        # ezdxf 1.1 omits common entity flag 60 when writing fixtures. Supply
        # the parsed entity state directly so the invisible flag is preserved.
        with patch('cad_reader.ezdxf.readfile',return_value=doc):
            paths,_,_=load_dxf('visibility.dxf',.01,1)
        self.assertEqual(len(paths),2)
        self.assertEqual(bounds(paths),(300,0,420,10))

    def test_layer_zero_inherits_through_nested_blocks_while_explicit_layers_remain_visible(self):
        doc=ezdxf.new();doc.layers.new('off').off();doc.layers.new('visible')
        inner=doc.blocks.new('inner')
        rectangle(inner,100);rectangle(inner,300,'visible')
        outer=doc.blocks.new('outer');outer.add_blockref('inner',(50,0))
        doc.modelspace().add_blockref('outer',(1000,0),dxfattribs={'layer':'off'})
        paths,_,_=self.read(doc)
        self.assertEqual(len(paths),1)
        self.assertEqual(bounds(paths),(1350,0,1370,10))

    def test_hidden_attribute_does_not_trigger_missing_font_error(self):
        doc=ezdxf.new();block=doc.blocks.new('part');rectangle(block)
        doc.styles.get('Standard').dxf.font='missing.shx'
        insert=doc.modelspace().add_blockref('part',(0,0))
        insert.add_attrib('LABEL','hidden',dxfattribs={'flags':1})
        paths,_,_=self.read(doc)
        self.assertEqual(len(paths),1)

    def test_saved_ucs_does_not_move_or_rotate_world_geometry(self):
        doc=ezdxf.new();entity=rectangle(doc.modelspace())
        ucs=UCS(origin=(2404,-2639,0),ux=(0,1,0),uy=(-1,0,0))
        entity.transform(ucs.matrix)
        doc.header['$UCSORG']=ucs.origin;doc.header['$UCSXDIR']=ucs.ux;doc.header['$UCSYDIR']=ucs.uy
        paths,_,_=self.read(doc)
        self.assertEqual(bounds(paths),(2394,-2639,2404,-2619))
        manual=[[transform(v,(5,2),0,2) for v in p] for p in paths]
        self.assertEqual(bounds(manual),(4778,-5282,4798,-5242))
        world,_,_=self.read(doc,'wcs')
        self.assertEqual(bounds(world),(2394,-2639,2404,-2619))

    def test_saved_ucs_is_ignored_for_text_hatch_and_solids(self):
        for kind in ('TEXT','MTEXT','HATCH','SOLID','LWPOLYLINE'):
            with self.subTest(kind=kind):
                doc=ezdxf.new();doc.styles.get('Standard').dxf.font='DejaVuSans.ttf'
                space=doc.modelspace()
                if kind=='TEXT':entity=space.add_text('X',dxfattribs={'insert':(5,6),'height':20})
                elif kind=='MTEXT':entity=space.add_mtext('C',dxfattribs={'insert':(5,26),'char_height':20})
                elif kind=='HATCH':
                    entity=space.add_hatch()
                    entity.paths.add_polyline_path([(0,0),(20,0),(20,10),(0,10)],is_closed=True)
                elif kind=='SOLID':entity=space.add_solid([(0,0),(20,0),(0,10),(20,10)])
                else:entity=rectangle(space)
                original,_,_=self.read(doc,'wcs')
                ucs=UCS(origin=(100,200,300),ux=(1,0,0),uy=(0,0,1))
                entity.transform(ucs.matrix)
                doc.header['$UCSORG']=ucs.origin;doc.header['$UCSXDIR']=ucs.ux;doc.header['$UCSYDIR']=ucs.uy
                actual,_,_=self.read(doc)
                doc.header['$UCSORG']=(0,0,0);doc.header['$UCSXDIR']=(1,0,0);doc.header['$UCSYDIR']=(0,1,0)
                expected,_,_=self.read(doc)
                self.assertEqual(actual,expected)

    def test_block_transform_and_drawing_transform_are_not_applied_twice(self):
        doc=ezdxf.new();block=doc.blocks.new('part');rectangle(block)
        doc.modelspace().add_blockref('part',(2404,-2639))
        doc.header['$UCSORG']=(2404,-2639,0)
        paths,_,_=self.read(doc)
        self.assertEqual(bounds(paths),(2404,-2639,2424,-2629))

    def test_invalid_saved_ucs_has_no_effect_and_explicit_ucs_is_rejected(self):
        doc=ezdxf.new();rectangle(doc.modelspace())
        doc.header['$UCSXDIR']=(1,0,0);doc.header['$UCSYDIR']=(1,0,0)
        self.assertEqual(bounds(self.read(doc)[0]),(0,0,20,10))
        with self.assertRaisesRegex(ValueError,'WCS'):
            self.read(doc,'ucs')
        self.assertEqual(bounds(self.read(doc,'wcs')[0]),(0,0,20,10))

    def test_1118_template_keeps_world_location_and_only_13_visible_contours(self):
        file=Path(__file__).parent/'test_data'/'template_1118.dxf'
        paths,notes,units=load_dxf(file,.1,1)
        self.assertEqual(units,4)
        self.assertEqual(len(paths),13)
        for actual,expected in zip(bounds(paths),(2404.263602163644,-2638.3657817635544,5306.291941421717,-2338.365781763552)):
            self.assertAlmostEqual(actual,expected,places=7)
        self.assertTrue(any('18' in note and 'background' in note for note in notes))
        planned,_=plan_paths(paths,'outline')
        self.assertEqual(len(planned),13)
        world,_,_=load_dxf(file,.1,1,coordinate_system='wcs')
        self.assertAlmostEqual(solid_region(paths)[0].area,solid_region(world)[0].area,places=6)

    def test_saved_coordinate_choice_preserves_the_import_folder(self):
        import file_preferences as prefs
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'ui.json';drawing=Path(directory)/'part.dxf'
            with patch.object(prefs,'PREFERENCES_FILE',file):
                self.assertEqual(prefs.cad_coordinate_system(),'wcs')
                file.write_text('{"cad_coordinate_system":"ucs"}',encoding='utf-8')
                self.assertEqual(prefs.cad_coordinate_system(),'wcs')
                prefs.remember_import_directory(drawing)
                prefs.remember_cad_coordinate_system('wcs')
                self.assertEqual(prefs.cad_coordinate_system(),'wcs')
                with self.assertRaises(ValueError):prefs.remember_cad_coordinate_system('ucs')
                self.assertEqual(Path(prefs.import_directory()),Path(directory).resolve())
                prefs.remember_import_directory(drawing)
                self.assertEqual(prefs.cad_coordinate_system(),'wcs')


if __name__=='__main__':
    unittest.main()
