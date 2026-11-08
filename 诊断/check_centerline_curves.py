"""Centerline curve reproduction and installed-font audit (offline)."""
import sys,json,argparse,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'工程'/'.vendor'),str(ROOT/'工程')]
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from shapely.geometry import LineString,Point
from shapely.ops import unary_union,polygonize
from direct_text import TextSpec,text_boundaries,available_fonts
from font_support import character_codes
from welding import (solid_region,plan_paths,polygons_of,boundary_midlines,
                     straight_priority_trails)

OUT=ROOT/'诊断'/'中心线曲线修复';OUT.mkdir(exist_ok=True)


def font_files():
    available=available_fonts();result=[]
    for name in ('ZITI1','ZITI2','Arial','DejaVu Sans','Times New Roman','Verdana',
                 'Microsoft YaHei','SimHei','SimSun','KaiTi'):
        try:
            if name.startswith('ZITI'):
                file=next(f for f in available.values() if Path(f).name.lower()==name.lower()+'.ttf')
            else:file=font_manager.findfont(font_manager.FontProperties(family=[name]),fallback_to_default=False)
            result.append((name,file))
        except (ValueError,StopIteration):continue
    return result


def metrics(region,paths,resolution):
    line=unary_union([LineString(p) for p in paths])
    record={'paths':len(paths),'vertices':sum(map(len,paths)),
            'outside_mm':line.difference(region.buffer(1e-6)).length,
            'finite':all(__import__('math').isfinite(v) for p in paths for point in p for v in point)}
    polys=polygons_of(region)
    faces=list(polygonize(line))
    from shapely.geometry import Polygon
    record['holes']=sum(len(poly.interiors) for poly in polys)
    record['holes_enclosed']=all(any(face.buffer(1e-6).covers(Polygon(hole)) for face in faces)
                                 for poly in polys for hole in poly.interiors)
    record['repeated_length_mm']=sum(LineString(p).length for p in paths)-line.length
    if len(polys)==1 and len(polys[0].interiors)==1 and len(paths)==1 and paths[0][0]==paths[0][-1]:
        outer,inner=polys[0].exterior,polys[0].interiors[0]
        count=max(40,min(3000,int(line.length/max(resolution*2,.1))))
        differences=[]
        for i in range(count):
            p=line.interpolate(i/count,normalized=True)
            differences.append(abs(outer.distance(p)-inner.distance(p)))
        record['ring_imbalance_mm']=max(differences)
    return record


def reproduce(phase):
    name,file=font_files()[0]
    raw=text_boundaries(TextSpec(text='NO',font_file=file,height=400))
    paths,_=plan_paths(raw,'centerline',resolution=.2)
    region,_=solid_region(raw)
    data={'font':name,'text':'NO','height':400,'raw':raw,'paths':paths,'metrics':metrics(region,paths,.2)}
    poly=max((p for p in polygons_of(region) if p.interiors),key=lambda p:p.area)
    local=boundary_midlines(poly,.2)
    data['o_medial']=local
    o_paths=[p for p in paths if poly.buffer(1e-6).covers(LineString(p))]
    data['o_metrics']=metrics(poly,o_paths,.2)
    (OUT/(phase+'-NO.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    print(phase,data['o_metrics'],flush=True)


def audit(phase,gallery=False,lowercase=False):
    results=[]
    for name,file in font_files():
        codes=character_codes(file,Path(file).stat().st_mtime_ns)
        glyphs='abcdefghijklmnopqrstuvwxyz' if lowercase else 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        if gallery:
            fig,axes=plt.subplots(6,6,figsize=(12,13),dpi=130)
            fig.suptitle(name+' - centerlines / original boundaries',fontsize=18)
        for index,ch in enumerate(glyphs):
            if ord(ch) not in codes:continue
            raw=text_boundaries(TextSpec(text=ch,font_file=file,height=40))
            region,_=solid_region(raw)
            try:
                paths,_=plan_paths(raw,'centerline',resolution=.2)
                record=metrics(region,paths,.2)
                # A closed annulus should remain close to the two boundaries'
                # equidistant medial loop; being merely inside is insufficient.
                record['curved_ring_checked']=ch in 'O0o' and 'ring_imbalance_mm' in record
                record['ok']=record['finite'] and record['outside_mm']<1e-5 and record['holes_enclosed'] and (not record['curved_ring_checked'] or record['ring_imbalance_mm']<=.6)
            except ValueError as exc:
                paths=[];record={'ok':False,'error':str(exc),'policy_rejected':'中心线模式不适用' in str(exc)}
            results.append({'font':name,'glyph':ch,**record})
            if gallery:
                ax=axes.flat[index]
                for p in raw:ax.plot(*zip(*p),color='#cbd5e1',linewidth=.7)
                for p in paths:ax.plot(*zip(*p),color='#2563eb',linewidth=1)
                ax.set_title(ch);ax.set_aspect('equal');ax.axis('off')
        if gallery:
            for index,ch in enumerate(glyphs):
                if ord(ch) not in codes:axes.flat[index].axis('off')
            fig.tight_layout(rect=(0,0,1,.97));fig.savefig(OUT/(phase+'-'+name.replace(' ','_')+'-glyphs.png'));plt.close(fig)
        print(name,len([r for r in results if r['font']==name]),flush=True)
        suffix='-lowercase-audit.json' if lowercase else '-font-audit.json'
        (OUT/(phase+suffix)).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('cases',len(results),'flagged',sum(not r['ok'] for r in results),'policy_rejected',sum(r.get('policy_rejected',False) for r in results),flush=True)


def plot():
    before=json.loads((OUT/'before-NO.json').read_text(encoding='utf-8'))
    after=json.loads((OUT/'after-NO.json').read_text(encoding='utf-8'))
    fig,axes=plt.subplots(1,2,figsize=(14,5),dpi=140)
    for ax,data,title in zip(axes,(before,after),('BEFORE - curve replaced by straight corners','AFTER - preserve original rounded centerline')):
        for p in data['raw']:ax.plot(*zip(*p),color='#cbd5e1',linewidth=1)
        for p in data['paths']:ax.plot(*zip(*p),linewidth=1.2)
        ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_title(title);ax.set_xlabel('X (mm)');ax.set_ylabel('Y (mm)')
    fig.tight_layout();fig.savefig(OUT/'NO-before-after.png');plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('before','after'));parser.add_argument('--audit',action='store_true');parser.add_argument('--gallery',action='store_true');parser.add_argument('--lowercase',action='store_true')
    args=parser.parse_args()
    if args.phase=='before':
        # Trusted snapshot extracted from our own last published application.
        # Keep an immutable baseline after the production source is fixed.
        import marshal,types
        snapshot=OUT/'published-welding-before.marshal'
        module=types.ModuleType('welding_published_before')
        with snapshot.open('rb') as source:exec(marshal.load(source),module.__dict__)
        plan_paths=module.plan_paths
    reproduce(args.phase)
    if args.audit:audit(args.phase,gallery=args.gallery)
    if args.lowercase:audit(args.phase,lowercase=True)
    if args.phase=='after':plot()
