"""Regenerate the Drawing1 DXF centerline preview and validation report."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent / '.vendor'))
import json
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from shapely.geometry import LineString
from cad_reader import load_dxf
from welding import plan_paths, solid_region
from geometry import urscript

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / '输出结果'

def validate():
    OUTPUT.mkdir(exist_ok=True)
    import ezdxf
    texts = [e.plain_text() for e in ezdxf.readfile(str(ROOT / 'CAD图纸' / 'Drawing1.dxf')).modelspace() if e.dxftype() in ('TEXT','MTEXT')]
    if texts != ['AAA']:
        raise ValueError('Drawing1 has changed: this validator requires the original AAA sample')
    raw,warnings,_=load_dxf(str(ROOT / 'CAD图纸' / 'Drawing1.dxf'),0.05,1)
    region,_=solid_region(raw)
    paths,notes=plan_paths(raw,'centerline')
    assert len(paths)==6, 'AAA should have three continuous arches and three crossbars'
    assert all(region.buffer(1e-7).covers(LineString(p)) for p in paths)
    assert sorted(map(len,paths)) == [2,2,2,4,4,4], 'Long legs should remain straight, with short crown bridges'
    figure=Figure(figsize=(12,5));FigureCanvasAgg(figure)
    ax=figure.add_subplot(111)
    for p in raw:
        x,y=zip(*p);ax.plot(x,y,color='lightgray',linewidth=1.5)
    for p in paths:
        x,y=zip(*p);ax.plot(x,y,linewidth=1.2);ax.plot(x[0],y[0],'go',markersize=3)
    ax.set_aspect('equal');ax.set_xlabel('User X (mm)');ax.set_ylabel('User Y (mm)')
    figure.tight_layout();figure.savefig(str(OUTPUT / 'Drawing1_center_after.png'),dpi=150)
    (OUTPUT / 'Drawing1_validation.json').write_text(json.dumps({'source':'Drawing1.dxf (companion export; DWG not directly decoded)','trails':len(paths),'vertices_per_trail':list(map(len,paths)),'all_paths_inside':True,'warnings':warnings+notes},ensure_ascii=False,indent=2),encoding='utf-8')
    # Position this local drawing at the robot user origin before exporting.
    xmin,ymin,_,_=region.bounds
    local=[[(x-xmin,y-ymin) for x,y in p] for p in paths]
    (OUTPUT / 'Drawing1_center.script').write_text(urscript(local,0,20,10,0),encoding='utf-8')
    return paths

if __name__=='__main__':
    result=validate()
    print('Drawing1 validation OK:',len(result),'trails;',list(map(len,result)))
