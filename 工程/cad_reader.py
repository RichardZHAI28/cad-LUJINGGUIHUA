import math
import re
from pathlib import Path
import ezdxf
from ezdxf.path import make_path, from_hatch
from matplotlib.font_manager import FontProperties, findfont, fontManager
from font_support import CadFontError,font_key,load_font_mappings,refresh_fonts,require_glyphs
from cad_text import text_outlines
from cad_coordinates import drawing_transform

# Localized family names refer to the same installed font, not a substitute.
FONT_FAMILIES={'宋体':'SimSun','黑体':'SimHei','微软雅黑':'Microsoft YaHei',
               '微软雅黑 ui':'Microsoft YaHei UI','楷体':'KaiTi','仿宋':'FangSong','等线':'DengXian'}


def cad_font(doc, entity, mappings=None):
    """Resolve the DXF style font without silently replacing every glyph."""
    style=doc.styles.get(entity.dxf.get('style','Standard'))
    requested=style.dxf.get('font','')
    family_hint,italic,bold=style.get_extended_font_data()
    if entity.dxftype()=='MTEXT':
        overrides=re.findall(r'\\[fF]([^;]+);',entity.text)
        if overrides:
            if len(set(overrides))>1:
                raise CadFontError('这段多行文字含多种字体，目前尚不能逐段还原。可在 CAD 中统一字体，或将文字转换为几何边界。几何边界仍可用于中心线、实心填充及内外轮廓三种模式。')
            parts=overrides[0].split('|');requested=parts[0]
            bold='b1' in parts[1:];italic='i1' in parts[1:]
    name=requested.replace('\\','/').rsplit('/',1)[-1]
    mappings=load_font_mappings() if mappings is None else mappings
    mapped=mappings.get(font_key(requested))
    if mapped:
        if not Path(mapped).is_file():raise CadFontError('已导入的字体文件缺失，请在“参数设置 → 字体”重新导入：'+requested,requested)
        return FontProperties(fname=str(mapped)),requested+' → 用户指定字库 '+Path(mapped).name
    suffix=Path(name).suffix.lower()
    if suffix in ('.shx','.shp'):
        raise CadFontError('“{}”是 SHX/SHP 笔画字体，本版尚未接入原字库笔画解析。可在“参数设置 → 字体”明确指定替代字库，或在 CAD 中把文字转换为几何边界；转换后并不限于空心字焊接。'.format(name),requested)
    if suffix in ('.ttf','.otf','.ttc'):
        # Use installed fonts only, never arbitrary paths embedded in a drawing.
        match=next((font for font in fontManager.ttflist if Path(font.fname).name.lower()==name.lower() and Path(font.fname).is_file()),None)
        if match is None:
            refresh_fonts()
            match=next((font for font in fontManager.ttflist if Path(font.fname).name.lower()==name.lower() and Path(font.fname).is_file()),None)
        if match and not (bold or italic):return FontProperties(fname=match.fname),name
        family=match.name if match else (family_hint or Path(name).stem)
    else:
        family=name
    if not family:
        raise CadFontError('CAD 未指定字体。可在 CAD 中设置字体，或将文字转换为几何边界。转换后仍支持三种焊接模式。')
    family=FONT_FAMILIES.get(family.casefold(),family)
    properties=FontProperties(family=[family],weight='bold' if bold else 'normal',style='italic' if italic else 'normal')
    try:resolved=findfont(properties,fallback_to_default=False)
    except ValueError:
        refresh_fonts()
        try:resolved=findfont(properties,fallback_to_default=False)
        except ValueError:
            raise CadFontError('本机缺少 CAD 字体“{}”。请在“参数设置 → 字体”导入字库文件（TTF/OTF/TTC，无需安装到 Windows），或明确指定替代字体；也可在 CAD 中转为几何边界。这里的“字体轮廓”不等于只能做空心字。'.format(requested),requested)
    return FontProperties(fname=resolved),requested


def load_dxf(filename, tolerance, text_scale, coordinate_system='wcs'):
    if tolerance <= 0 or text_scale <= 0:
        raise ValueError('曲线精度和字号倍率必须大于 0')
    doc = ezdxf.readfile(filename)
    paths, warnings = [], []
    projection, coordinate_note = drawing_transform(doc, coordinate_system)
    if coordinate_note:
        warnings.append(coordinate_note)
    hidden = {}

    def project(vertex):
        point = projection.transform(vertex) if projection is not None else vertex
        return (point.x, point.y)

    def extract(entity, parent_layer=None):
        kind = entity.dxftype()
        try:
            layer_name = entity.dxf.get('layer', '0')
            if layer_name == '0' and parent_layer is not None:
                layer_name = parent_layer
            try:
                layer = doc.layers.get(layer_name)
            except ezdxf.DXFTableEntryError:
                layer = None
            # A frozen INSERT hides the entire block. With an off INSERT layer,
            # explicit child layers can remain visible; layer-0 children inherit
            # the reference layer and are filtered individually.
            invisible = (bool(entity.dxf.get('invisible', 0))
                         or (kind == 'ATTRIB' and entity.is_invisible)
                         or (layer is not None and layer.is_frozen())
                         or (kind != 'INSERT' and layer is not None and layer.is_off()))
            if invisible:
                hidden[layer_name] = hidden.get(layer_name, 0) + 1
                return
            if kind == 'INSERT':
                for child in entity.virtual_entities():
                    extract(child, layer_name)
                for attrib in entity.attribs:
                    extract(attrib, layer_name)
            elif kind in ('TEXT', 'MTEXT', 'ATTRIB'):
                text = entity.plain_text()
                font,font_name=cad_font(doc,entity)
                require_glyphs(font,text,requested=entity.dxf.get('style','Standard') if not font_name else font_name.split(' → ')[0])
                paths.extend(text_outlines(entity,font,text_scale,coordinate_transform=projection))
                warnings.append('{}：使用 CAD 字体 {}，按图纸文字定位点、对齐方式和字高布局。'.format(kind,font_name))
                if kind=='MTEXT' and entity.dxf.get('line_spacing_style',1)==2:
                    warnings.append('此段文字使用固定行距；混合字高时的固定行距尚未完整还原，请核对 CAD。')
                if ' → ' in font_name:warnings.append('已使用用户指定字库，字形可能与原 CAD 不同；请核对预览后生成机器人程序。')
            elif kind in ('HATCH', 'MPOLYGON'):
                for boundary in from_hatch(entity):
                    for subpath in boundary.sub_paths():
                        contour = [project(v) for v in subpath.flattening(tolerance)]
                        if contour and contour[0] != contour[-1]:
                            contour.append(contour[0])
                        if len(contour) >= 4:
                            paths.append(contour)
            elif kind == 'SOLID':
                vertices = list(entity.wcs_vertices())
                contour = [project(v) for v in vertices]
                if contour and contour[0] != contour[-1]:
                    contour.append(contour[0])
                paths.append(contour)
            elif kind in ('LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'ELLIPSE', 'SPLINE'):
                contour = [project(v) for v in make_path(entity).flattening(tolerance)]
                if len(contour) > 1:
                    paths.append(contour)
            else:
                warnings.append('跳过未支持实体：' + kind)
            if kind != 'INSERT' and entity.dxf.is_supported('elevation') and abs(entity.dxf.get('elevation', 0) if isinstance(entity.dxf.get('elevation', 0), (float, int)) else 0) > 1e-6:
                warnings.append('检测到高程；当前仅使用所选图纸坐标系的 XY 平面投影')
        except CadFontError:
            raise
        except Exception as exc:
            warnings.append('{} 提取失败：{}'.format(kind, exc))

    for entity in doc.modelspace():
        extract(entity)
    if hidden:
        warnings.append('已跳过 {} 个隐藏或冻结实体/块（{}）；不参与预览和轨迹。'.format(
            sum(hidden.values()), '；'.join('{}：{}'.format(name, count) for name, count in sorted(hidden.items()))))
    return paths, sorted(set(warnings)), doc.header.get('$INSUNITS', 0)

