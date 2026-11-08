import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'工程'/'.vendor'),str(ROOT/'工程'),str(ROOT/'诊断')]
import welding
from direct_text import TextSpec,text_boundaries
from check_centerline_curves import font_files
import matplotlib;matplotlib.use('Agg')
from matplotlib import pyplot as plt
OUT=ROOT/'诊断'/'端面收缩优先'
spec=importlib.util.spec_from_file_location('before',OUT/'welding_before.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
file=next(file for name,file in font_files() if name=='ZITI2')
fig,axes=plt.subplots(2,3,figsize=(10,8))
fig.suptitle('ZITI2 / Before: line intersections first | After: equal-offset collisions first')
for col,glyph in enumerate('AMN'):
 raw=text_boundaries(TextSpec(text=glyph,font_file=file,height=400))
 region,_=welding.solid_region(raw)
 for row,module in enumerate((old,welding)):
  paths,_=module.center_paths(region,.2);ax=axes[row,col]
  for p in raw:ax.plot(*zip(*p),color='#cbd5e1',lw=1)
  for p in paths:ax.plot(*zip(*p),lw=1.6)
  ax.set_title(('Before ' if row==0 else 'After ')+glyph)
  ax.set_aspect('equal');ax.axis('off')
fig.tight_layout();fig.savefig(OUT/'AMN-preview.png',dpi=140)
