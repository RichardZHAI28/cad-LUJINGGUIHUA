"""Per-user font imports and explicit CAD-font substitutions, without OS installs."""
import hashlib
import json
import shutil
import os
from functools import lru_cache
from pathlib import Path
from matplotlib import font_manager,ft2font
from runtime_paths import DATA_ROOT,CONFIG_FILE

FONT_DIR=DATA_ROOT/'字体'
FONT_MAP_FILE=CONFIG_FILE.parent/'font_mappings.json'
_scanned=False


class CadFontError(ValueError):
    def __init__(self,message,font_name=''):
        super().__init__(message)
        self.font_name=font_name


def font_key(name):
    return str(name).replace('\\','/').rsplit('/',1)[-1].strip().casefold()


def load_font_mappings(path=None,font_dir=None):
    path=Path(path or FONT_MAP_FILE);folder=Path(font_dir or FONT_DIR)
    if not path.exists():return {}
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        result={}
        for alias,name in data.items():
            if not isinstance(name,str) or Path(name).name!=name or '/' in name or '\\' in name:
                raise ValueError('字库文件名不合法')
            result[font_key(alias)]=str(folder/name)
        return result
    except (ValueError,TypeError,AttributeError) as exc:
        raise CadFontError('字体映射配置无法读取，请在“参数设置 → 字体”中检查：'+str(exc))


def save_font_mappings(mappings,path=None,font_dir=None):
    path=Path(path or FONT_MAP_FILE);folder=Path(font_dir or FONT_DIR).resolve()
    data={}
    for alias,file in mappings.items():
        file=Path(file).resolve()
        if file.parent!=folder:raise ValueError('映射字体必须位于软件字库目录')
        data[font_key(alias)]=file.name
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def import_font(source,alias,font_dir=None,map_file=None):
    source=Path(source)
    if source.suffix.lower() not in ('.ttf','.otf','.ttc'):
        raise ValueError('请选择 TTF、OTF 或 TTC 字库；SHX 不能作为 TrueType 字库直接导入')
    alias=font_key(alias)
    if not alias:raise ValueError('请填写图纸中的原字体名称，例如 simsun.ttc 或 txt.shx')
    face=ft2font.FT2Font(str(source))  # Validate before copying or changing mappings.
    name=face.family_name;del face
    folder=Path(font_dir or FONT_DIR);folder.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    target=folder/(digest+'_'+source.name)
    if not target.exists():shutil.copy2(source,target)
    font_manager.fontManager.addfont(str(target))
    mappings=load_font_mappings(map_file,folder)
    mappings[alias]=str(target)
    save_font_mappings(mappings,map_file,folder)
    return name


def refresh_fonts(force=False):
    global _scanned
    if _scanned and not force:return 0
    known={str(Path(f.fname).resolve()) for f in font_manager.fontManager.ttflist if Path(f.fname).is_file()}
    files=set(font_manager.findSystemFonts(fontext='ttf'))
    if os.name == 'nt':
        # Matplotlib's registry scan can omit fonts installed for this user.
        local = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))/'Microsoft/Windows/Fonts'
        if local.is_dir():
            files.update(str(p) for p in local.iterdir() if p.suffix.lower() in ('.ttf','.otf','.ttc'))
    if FONT_DIR.exists():files.update(str(p) for p in FONT_DIR.iterdir() if p.suffix.lower() in ('.ttf','.otf','.ttc'))
    count=0
    for file in sorted(files):
        if str(Path(file).resolve()) in known:continue
        try:font_manager.fontManager.addfont(file);count+=1
        except (OSError,RuntimeError,ValueError):continue
    _scanned=True
    return count


@lru_cache(maxsize=64)
def character_codes(file,stamp):
    return frozenset(ft2font.FT2Font(file).get_charmap())


def require_glyphs(font,text,requested,recovery='参数设置 → 字体'):
    file=Path(font.get_file())
    codes=character_codes(str(file),file.stat().st_mtime_ns)
    missing=sorted({ch for ch in text if not ch.isspace() and ord(ch) not in codes})
    if missing:
        raise CadFontError('字体“{}”不包含这些字符：{}。请在“{}”导入包含这些字符的字库或选择替代字库，避免生成方框焊道。'.format(requested,' '.join(missing[:12]),recovery),requested)
