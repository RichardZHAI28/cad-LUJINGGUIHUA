"""Default spatial weld order in the user frame, independent of CAD entity order."""
import math
from shapely.geometry import LineString
from welding import solid_region, polygons_of


def near_zero(lo,hi):
    return min(max(0.0,lo),hi)


def axis_order(value):
    # Positive user axes first; negative coordinates follow from zero outward.
    return (0,value) if value>=0 else (1,-value)


def row_order(items,anchor,tolerance,bounds=None):
    # Anchor-based grouping avoids transitive drift across many adjacent rows.
    rows=[]
    for item in sorted(items,key=lambda p:(axis_order(anchor(p)[1]),axis_order(anchor(p)[0]))):
        x,y=anchor(item)
        def same_row(row):
            if abs(y-row[0])<=tolerance:return True
            if bounds is None:return False
            # A Q tail or a descender must not create a new earlier row.
            # Compare with the fixed row representative, never a growing union.
            _,lo,_,hi=bounds(item)
            _,rlo,_,rhi=bounds(row[1][0])
            shorter=min(hi-lo,rhi-rlo)
            overlap=min(hi,rhi)-max(lo,rlo)
            return shorter>1e-9 and overlap>=shorter*.5
        target=next((r for r in rows if same_row(r)),None)
        if target is None:
            target=[y,[]];rows.append(target)
        target[1].append(item)
    result=[]
    for y,row in sorted(rows,key=lambda r:axis_order(r[0])):
        result.extend(sorted(row,key=lambda p:(axis_order(anchor(p)[0]),axis_order(anchor(p)[1]))))
    return result


def start_near_origin(path):
    path=[tuple(p) for p in path]
    if path[0]!=path[-1]:
        return path if math.hypot(*path[0])<=math.hypot(*path[-1]) else list(reversed(path))
    # Project origin onto the nearest segment, so the start does not depend on
    # which vertex the CAD application happened to store first.
    candidates=[]
    for i,(a,b) in enumerate(zip(path,path[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1]
        den=dx*dx+dy*dy
        t=max(0,min(1,-(a[0]*dx+a[1]*dy)/den)) if den else 0
        p=(a[0]+t*dx,a[1]+t*dy)
        candidates.append((math.hypot(*p),p,i))
    _,p,i=min(candidates)
    ring=path[:-1]
    ordered=[p]+ring[i+1:]+ring[:i+1]+[p]
    return [q for j,q in enumerate(ordered) if j==0 or q!=ordered[j-1]]


def order_weld_paths(paths,boundaries,mode,row_tolerance=5.0):
    if not math.isfinite(row_tolerance) or row_tolerance<0:
        raise ValueError('行归并容差须为不小于 0 的有限数值')
    region,_=solid_region(boundaries)
    polygons=polygons_of(region)
    groups={i:[] for i in range(len(polygons))}
    safe=[poly.buffer(1e-7) for poly in polygons]
    for path in paths:
        line=LineString(path)
        owner=next((i for i,poly in enumerate(safe) if poly.covers(line)),None)
        if owner is None:
            raise ValueError('焊道无法归属到单个实体，请检查轨迹是否越界或跨越图形')
        groups[owner].append(path)
    def group_anchor(i):
        x0,y0,x1,y1=polygons[i].bounds
        return near_zero(x0,x1),near_zero(y0,y1)
    ordered=[]
    for index in row_order([i for i in groups if groups[i]],group_anchor,row_tolerance,lambda i:polygons[i].bounds):
        local=groups[index]
        if mode!='fill':
            local=[start_near_origin(path) for path in local]
            local=row_order(local,lambda p:p[0],row_tolerance)
        # Fill direction, layer order and continuous welding must remain intact.
        ordered.extend(local)
    return ordered
