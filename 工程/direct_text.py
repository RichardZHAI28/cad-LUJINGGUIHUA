"""Literal typed text -> closed font boundaries in CAD world millimetres."""
from dataclasses import dataclass, asdict
from pathlib import Path
import math
from matplotlib import font_manager
from font_support import refresh_fonts, require_glyphs, CadFontError
from cad_text import FontGeometry


@dataclass
class TextSpec:
    text: str = '0123456789'
    font_file: str = ''
    height: float = 30.0
    x: float = 0.0
    y: float = 0.0
    line_spacing: float = 1.5

    def to_dict(self):
        return asdict(self)


def available_fonts():
    refresh_fonts()
    entries = {}
    for font in font_manager.fontManager.ttflist:
        path = Path(font.fname)
        if path.is_file():
            label = '{} · {} · {}'.format(font.name, font.style, path.name)
            if label in entries and str(path.resolve()) != entries[label]:
                label += ' · ' + str(path.parent)
            entries[label] = str(path.resolve())
    return dict(sorted(entries.items(), key=lambda item: (
        0 if 'ziti1' in item[0].casefold() else 1 if 'ziti2' in item[0].casefold() else 2,
        item[0].casefold())))


def text_boundaries(spec, text_scale=1):
    if not spec.text.strip():
        raise ValueError('请输入要生成轨迹的文字或数字')
    if len(spec.text) > 2000:
        raise ValueError('一次最多输入 2000 个字符，请分批生成')
    if any(ord(ch) < 32 and ch not in '\n\r\t' for ch in spec.text):
        raise ValueError('文字中含有不支持的控制字符')
    if not all(math.isfinite(v) for v in (spec.height,spec.x,spec.y,spec.line_spacing,text_scale)):
        raise ValueError('文字尺寸和坐标必须为有限数值')
    if min(spec.height,text_scale) <= 0 or spec.line_spacing < 1:
        raise ValueError('字高、字号倍率须大于 0，行距倍率须不小于 1')
    file = Path(spec.font_file)
    if not file.is_file() or file.suffix.lower() not in ('.ttf','.ttc','.otf'):
        raise CadFontError('所选字库已缺失，请在“输入文字”中重新选择或导入字库',file.name)
    font = font_manager.FontProperties(fname=str(file))
    text = spec.text.replace('\r\n','\n').replace('\r','\n').expandtabs(4)
    require_glyphs(font,text,file.stem,'输入文字 → 当前字体 / 导入字库')
    geometry = FontGeometry(font)
    height = spec.height * text_scale
    paths = []
    for line_number,line in enumerate(text.split('\n')):
        if not line.strip():continue
        paths.extend([[(float(x),float(y)-line_number*height*spec.line_spacing) for x,y in polygon]
                      for polygon in geometry.polygons(line,height)])
    if not paths:
        raise ValueError('文字没有可用于焊接的封闭边界')
    # A deliberate, documented anchor for NEW text only; imported CAD is never
    # normalized to its bounding box. Preserve spacing between lines/glyphs.
    left = min(x for path in paths for x,y in path)
    bottom = min(y for path in paths for x,y in path)
    return [[(x-left+spec.x,y-bottom+spec.y) for x,y in path] for path in paths]
