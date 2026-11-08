"""Versioned old/new geometry comparison, timing and reproducible font audit."""
import importlib.util,json,sys,time,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'工程'/'.vendor'),str(ROOT/'工程'),str(ROOT/'诊断')]
import welding as new
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from shapely.geometry import LineString
from direct_text import TextSpec,text_boundaries
import check_centerline_curves as audit
OUT=ROOT/'诊断'/'端面收缩优先';OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('welding_before_equal_offset',OUT/'welding_before.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
parser=argparse.ArgumentParser();parser.add_argument('--audit',action='store_true');args=parser.parse_args()
results=[]
for family,file in audit.font_files()[:3]:
    fig,axes=plt.subplots(2,6,figsize=(18,6));fig.suptitle(family+' / before (top), equal offset collisions (bottom)')
    for col,ch in enumerate('MNACKS' if family!='ZITI1' else 'MNGKCS'):
        raw=text_boundaries(TextSpec(text=ch,font_file=file,height=400));region,_=new.solid_region(raw)
        start=time.perf_counter();before,_=old.center_paths(region,.2);before_s=time.perf_counter()-start
        new._cached_center_paths.cache_clear()
        start=time.perf_counter();after,_=new.center_paths(region,.2);after_s=time.perf_counter()-start
        start=time.perf_counter();cached,_=new.center_paths(region,.2);cached_s=time.perf_counter()-start
        assert after==cached
        xy=[point for path in after for point in path]
        old_xy=[point for path in before for point in path]
        lo_y,hi_y=region.bounds[1],region.bounds[3]
        record={'font':family,'glyph':ch,'before_paths':len(before),'after_paths':len(after),'before_s':before_s,'after_s':after_s,'cached_s':cached_s,
                'old_bottom_inset_mm':min(p[1] for p in old_xy)-lo_y,'old_top_inset_mm':hi_y-max(p[1] for p in old_xy),
                'bottom_inset_mm':min(p[1] for p in xy)-lo_y,'top_inset_mm':hi_y-max(p[1] for p in xy),**audit.metrics(region,after,.2)}
        assert record['outside_mm']<1e-5 and record['holes_enclosed'] and record['repeated_length_mm']<1e-6
        results.append(record)
        for row,paths in enumerate((before,after)):
            ax=axes[row,col]
            for p in raw:ax.plot(*zip(*p),color='#cbd5e1',lw=.8)
            for p in paths:ax.plot(*zip(*p),lw=1.3)
            ax.set_title(ch+' / '+str(len(paths)));ax.set_aspect('equal');ax.axis('off')
    fig.tight_layout();fig.savefig(OUT/(family+'-comparison.png'),dpi=130);plt.close(fig)
(OUT/'comparison.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
summary={'cases':len(results),'before_s':sum(r['before_s'] for r in results),'after_s':sum(r['after_s'] for r in results),'max_cold_glyph_s':max(r['after_s'] for r in results),'max_cached_s':max(r['cached_s'] for r in results),'paths':[(r['font'],r['glyph'],r['before_paths'],r['after_paths']) for r in results]}
(OUT/'timing.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2),flush=True)
if args.audit:
    audit.OUT=OUT
    audit.audit('after',gallery=True)
    audit.audit('after',lowercase=True)




