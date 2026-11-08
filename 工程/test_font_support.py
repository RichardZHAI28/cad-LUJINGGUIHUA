import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.vendor'))
import tempfile
import unittest
from unittest.mock import patch
import ezdxf
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties,findfont
from font_support import import_font,load_font_mappings,CadFontError,require_glyphs
from cad_reader import load_dxf,cad_font
from welding import plan_paths


class FontTests(unittest.TestCase):
    def test_localized_font_name_uses_the_same_font_instead_of_requesting_install(self):
        try:file=findfont(FontProperties(family=['SimSun']),fallback_to_default=False)
        except ValueError:self.skipTest('SimSun is not installed')
        doc=ezdxf.new();doc.styles.get('Standard').dxf.font='宋体'
        entity=doc.modelspace().add_text('中文')
        font,_=cad_font(doc,entity,mappings={})
        self.assertEqual(Path(font.get_file()).resolve(),Path(file).resolve())

    def test_private_import_and_explicit_shx_substitution_support_all_modes(self):
        source=findfont(FontProperties(family=['DejaVu Sans']),fallback_to_default=False)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);fonts=folder/'字体测试';mapping=folder/'mappings.json'
            with patch('font_support.FONT_DIR',fonts),patch('font_support.FONT_MAP_FILE',mapping),patch.object(font_manager.fontManager,'ttflist',list(font_manager.fontManager.ttflist)):
                doc=ezdxf.new();doc.styles.get('Standard').dxf.font='some_cad_font.shx'
                doc.modelspace().add_text('ABQ',dxfattribs={'height':30})
                file=folder/'drawing.dxf';doc.saveas(file)
                with self.assertRaises(CadFontError):load_dxf(file,.1,1)
                import_font(source,'SOME_CAD_FONT.SHX')
                self.assertTrue(mapping.is_file())
                loaded=load_font_mappings();private=Path(loaded['some_cad_font.shx'])
                self.assertEqual(private.parent,fonts)
                self.assertEqual(private.read_bytes(),Path(source).read_bytes())
                paths,warnings,_=load_dxf(file,.1,1)
                self.assertTrue(any('用户指定' in w for w in warnings))
                for mode in ('outline','fill','centerline'):
                    result,_=plan_paths(paths,mode,width=.8,resolution=.3)
                    self.assertTrue(result,mode)
                # Matplotlib caches FT2Font handles; release them before Windows
                # removes the temporary private-font directory.
                font_manager._get_font.cache_clear()
                font_manager.fontManager._findfont_cached.cache_clear()
                import gc
                gc.collect()
        font_manager.fontManager._findfont_cached.cache_clear()

    def test_bad_font_never_changes_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);file=folder/'invalid.ttf';file.write_bytes(b'not a font')
            with self.assertRaises((RuntimeError,ValueError)):
                import_font(file,'x.ttf',folder/'fonts',folder/'map.json')
            self.assertFalse((folder/'map.json').exists())
            with self.assertRaises(ValueError):import_font(folder/'x.shx','x.shx')

    def test_missing_chinese_glyph_is_reported_instead_of_rendered_as_box(self):
        font=FontProperties(fname=findfont(FontProperties(family=['DejaVu Sans']),fallback_to_default=False))
        require_glyphs(font,'ABQ 012','DejaVuSans.ttf')
        with self.assertRaises(CadFontError) as error:require_glyphs(font,'焊','DejaVuSans.ttf')
        self.assertIn('焊',str(error.exception));self.assertEqual(error.exception.font_name,'DejaVuSans.ttf')

    def test_refresh_recovers_a_missing_cached_font_path(self):
        actual=next(f for f in font_manager.fontManager.ttflist if Path(f.fname).name.lower()=='dejavusans.ttf' and Path(f.fname).is_file())
        doc=ezdxf.new();doc.styles.get('Standard').dxf.font='DejaVuSans.ttf'
        text=doc.modelspace().add_text('Q')
        with patch.object(font_manager.fontManager,'ttflist',[]),patch('cad_reader.refresh_fonts',side_effect=lambda:font_manager.fontManager.ttflist.append(actual)) as refresh:
            font,_=cad_font(doc,text,mappings={})
            self.assertEqual(font.get_file(),actual.fname);refresh.assert_called_once()
