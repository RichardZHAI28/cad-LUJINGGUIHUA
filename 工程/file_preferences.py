"""Remember the user's drawing folder separately from robot configuration."""
import json
from pathlib import Path
from runtime_paths import CONFIG_FILE, DRAWING_DIR

PREFERENCES_FILE = CONFIG_FILE.with_name('ui_preferences.json')


def _preferences():
    try:
        data = json.loads(PREFERENCES_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def import_directory(current_filename=None):
    """Prefer the current drawing, then the saved folder, then a valid fallback."""
    candidates = []
    if current_filename:
        candidates.append(Path(current_filename).parent)
    saved = _preferences().get('import_directory')
    if isinstance(saved, str) and saved.strip():
        candidates.append(saved)
    candidates.extend((DRAWING_DIR, Path.home()))
    for folder in candidates:
        try:
            directory = Path(folder)
            if directory.is_dir():
                return str(directory.resolve())
        except (OSError, ValueError):
            continue
    return str(Path.home())


def remember_import_directory(filename):
    directory = Path(filename).resolve().parent
    if not directory.is_dir():
        return
    data = _preferences()
    data['import_directory'] = str(directory)
    _save_preferences(data)


def _save_preferences(data):
    PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = PREFERENCES_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(PREFERENCES_FILE)


def cad_coordinate_system():
    # Old UCS preferences must never move a drawing in the new WCS-only UI.
    return 'wcs'


def remember_cad_coordinate_system(value):
    if value != 'wcs':
        raise ValueError('图纸固定使用世界坐标 WCS')
    data = _preferences()
    data['cad_coordinate_system'] = value
    _save_preferences(data)


def read_ui_setting(key, default=None):
    return _preferences().get(key, default)


def save_ui_setting(key, value):
    data = _preferences()
    data['cad_coordinate_system'] = 'wcs'
    data[key] = value
    _save_preferences(data)
