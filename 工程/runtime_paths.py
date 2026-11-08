"""Separate installed program resources from per-user writable data."""
import os
from pathlib import Path
import sys

FROZEN=bool(getattr(sys,'frozen',False))
SOURCE_ROOT=Path(__file__).resolve().parent.parent
if FROZEN:
    DATA_ROOT=Path(os.environ.get('CAD_WELD_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'CadWeldPlanner')))
else:
    DATA_ROOT=SOURCE_ROOT
DRAWING_DIR=DATA_ROOT/'CAD图纸'
OUTPUT_DIR=DATA_ROOT/'输出结果'
CONFIG_FILE=(DATA_ROOT/'配置'/'robot_profiles.json') if FROZEN else Path(__file__).resolve().parent/'robot_profiles.json'

def prepare():
    for folder in (DRAWING_DIR,OUTPUT_DIR,CONFIG_FILE.parent):folder.mkdir(parents=True,exist_ok=True)
    if FROZEN:
        os.environ.setdefault('MPLCONFIGDIR',str(DATA_ROOT/'cache'/'matplotlib'))
