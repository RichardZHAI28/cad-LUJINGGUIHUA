"""Convert closed solid boundaries to welding paths, in user-frame millimetres."""
import math
from functools import lru_cache
import numpy as np
import networkx as nx
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union,polygonize
from shapely.affinity import rotate
from scipy.spatial import Voronoi, QhullError
from shapely import linestrings,covers,prepare,from_wkb

MODES = {'中心线单道焊接': 'centerline', '实心排道填充': 'fill', '内外轮廓焊接': 'outline'}


def polygons_of(geometry):
    if geometry.geom_type == 'Polygon':
        return [geometry] if not geometry.is_empty else []
    return [p for g in getattr(geometry, 'geoms', []) for p in polygons_of(g)]


def lines_of(geometry):
    if geometry.geom_type in ('LineString', 'LinearRing'):
        return [list(geometry.coords)] if geometry.length > 1e-9 else []
    return [p for g in getattr(geometry, 'geoms', []) for p in lines_of(g)]


def solid_region(paths):
    rings, opens, warnings, seen = [], [], [], set()
    for path in paths:
        if len(path) < 4 or math.dist(path[0], path[-1]) > 1e-6:
            opens.append(path)
            continue
        # The accepted closure tolerance above must also be honoured here.
        # Flattened CAD arcs can end a few ulps beyond the first vertex; letting
        # Polygon add another closing edge then creates a microscopic spike.
        # Snap only the already-closed endpoint; real self intersections fail.
        poly = Polygon([*path[:-1],path[0]])
        if not poly.is_valid:
            raise ValueError('存在自交或无效封闭边界，请在 CAD 中修复后导入')
        if poly.area <= 1e-10:
            continue
        key = poly.normalize().wkb
        if key not in seen:
            seen.add(key)
            rings.append(poly)
    # Containment parity: outer material, inner void, nested islands.
    parents = []
    for i, ring in enumerate(rings):
        enclosing = [j for j, other in enumerate(rings) if j != i and other.area > ring.area and other.covers(ring)]
        parents.append(min(enclosing, key=lambda j: rings[j].area) if enclosing else None)
    def depth(i):
        return 0 if parents[i] is None else depth(parents[i])+1
    material = []
    for i, ring in enumerate(rings):
        if depth(i) % 2 == 0:
            holes = [list(rings[j].exterior.coords) for j in range(len(rings)) if parents[j] == i]
            material.append(Polygon(ring.exterior.coords, holes))
    region = unary_union(material)
    if opens:
        warnings.append('忽略 {} 条未封闭路径；三种实心加工模式只接受封闭区域'.format(len(opens)))
    return region, warnings


FILL_MODES = ('从上向下', '从左向右', '由外向内', '由内向外')


def boundary_paths(region):
    return [list(r.coords) for p in polygons_of(region) for r in [p.exterior, *p.interiors]]


def connect_ordered(paths, allowed):
    """Join adjacent passes only when the full connector stays in bead-safe area."""
    result = []
    for original in paths:
        path = list(original)
        if result:
            end = result[-1][-1]
            if path[0] == path[-1]:
                ring = path[:-1]
                i = min(range(len(ring)), key=lambda j: math.dist(end, ring[j]))
                path = ring[i:]+ring[:i]+[ring[i]]
            elif math.dist(end, path[-1]) < math.dist(end, path[0]):
                path.reverse()
            connector = LineString([end, path[0]])
            if allowed.buffer(1e-8).covers(connector):
                result[-1].extend(path if end != path[0] else path[1:])
                continue
        result.append(path)
    return result


def fill_paths(region, width, overlap, angle, direction='从上向下', continuous=False):
    if direction not in FILL_MODES:
        raise ValueError('未知填充方向')
    pitch = width*(1-overlap/100)
    rotated = rotate(region, -angle, origin=(0, 0))
    centers = rotated.buffer(-width/2, quad_segs=64)
    result = []
    if direction in ('由外向内', '由内向外'):
        layers = []
        for poly in polygons_of(centers):
            level = poly
            local = []
            while not level.is_empty:
                local.append(boundary_paths(level))
                if len(local) > 10000:
                    raise ValueError('填充层数过多，请增大道间距')
                # Offset from the original to avoid accumulating polygon errors.
                level = poly.buffer(-len(local)*pitch, quad_segs=64)
            if direction == '由内向外':
                local.reverse()
            layers.extend(local)
        result = [path for layer in layers for path in layer]
    else:
        for poly in polygons_of(centers):
            xmin, ymin, xmax, ymax = poly.bounds
            vertical = direction == '从左向右'
            span = xmax-xmin if vertical else ymax-ymin
            count = max(1, math.ceil(span/pitch))
            if count > 100000:
                raise ValueError('填充道数过多，请增大道间距')
            for i in range(count+1):
                if vertical:
                    x = xmin+span*i/count
                    scan = LineString([(x,ymin-width),(x,ymax+width)])
                else:
                    y = ymax-span*i/count
                    scan = LineString([(xmin-width,y),(xmax+width,y)])
                segments = lines_of(poly.intersection(scan))
                axis = 1 if vertical else 0
                segments = [sorted(line, key=lambda p:p[axis]) for line in segments]
                segments.sort(key=lambda line: line[0][axis])
                if continuous and i % 2:
                    segments = [list(reversed(line)) for line in reversed(segments)]
                result.extend(segments)
            # Boundary finishing pass ensures edge coverage after directional scans.
            result.extend(boundary_paths(poly))
    if continuous:
        result = connect_ordered(result, centers)
    paths = [list(rotate(LineString(line), angle, origin=(0, 0)).coords) for line in result]
    footprint = unary_union([LineString(line).buffer(width/2) for line in paths]) if paths else Polygon()
    residual = region.difference(footprint).area
    warnings = ['填充方向：{}；{}。'.format(direction, '连续焊接：仅合并实体内部可直连焊道，无法直连处仍熄弧抬升' if continuous else '每道独立起熄弧')]
    if residual > max(1e-5, region.area*0.001):
        warnings.append('按理想焊缝宽度估算仍有 {:.3f} mm² 未覆盖（尖角、窄笔画或偏置残余）；请调整焊缝宽度或重叠率。'.format(residual))
    return paths, warnings


def minimum_trails(paths, region, tolerance, prune):
    """Cover skeleton edges once with the minimum number of open trails.

    Pair odd vertices through a virtual hub, run Euler traversal, then remove
    virtual edges. No artificial welding connectors or repeated real edges.
    """
    graph = nx.MultiGraph()
    for path in paths:
        if len(path) > 1:
            graph.add_edge(tuple(path[0]), tuple(path[-1]), points=path)
    # Only remove short terminal spurs at a junction, never isolated strokes.
    remove = [(a,b,k) for a,b,k,d in graph.edges(keys=True,data=True)
              if a != b and ((graph.degree(a)==1 and graph.degree(b)>2) or
                              (graph.degree(b)==1 and graph.degree(a)>2))
              and LineString(d['points']).length < prune]
    graph.remove_edges_from(remove)
    result = []
    for nodes in nx.connected_components(graph):
        component = graph.subgraph(nodes).copy()
        if not component.number_of_edges():
            continue
        odd = [v for v,d in component.degree() if d % 2]
        hub = '__virtual_hub__'
        for v in odd:
            component.add_edge(hub, v, virtual=True)
        start = hub if odd else next(iter(component.nodes))
        current = []
        for a,b,k in nx.eulerian_circuit(component, source=start, keys=True):
            data = component[a][b][k]
            if data.get('virtual'):
                if current:
                    result.append(current)
                    current = []
                continue
            points = data['points']
            if tuple(points[0]) != a:
                points = list(reversed(points))
            current.extend(points if not current else points[1:])
        if current:
            result.append(current)
    simplified = []
    for path in result:
        line = LineString(path)
        candidate = line.simplify(tolerance, preserve_topology=True)
        # Smoothing must never cut through a hole or outside a concave stroke.
        simplified.append(list(candidate.coords) if region.covers(candidate) else path)
    return simplified


def validate_centerline_region(region):
    """Reject compact solid blobs before rasterization can invent short branches.

    A conservative geometric heuristic, not character recognition. Rings and
    elongated/branched strokes remain eligible for skeleton extraction.
    """
    rejected = []
    for index, poly in enumerate(polygons_of(region), 1):
        rectangle = list(poly.minimum_rotated_rectangle.exterior.coords)
        sides = [math.dist(a, b) for a, b in zip(rectangle, rectangle[1:])]
        aspect = max(sides)/max(min(sides), 1e-12)
        compactness = 4*math.pi*poly.area/(poly.length**2)
        if not poly.interiors and aspect <= 2.0 and compactness >= 0.60:
            xmin, ymin, xmax, ymax = poly.bounds
            rejected.append('区域 {}（X={:.2f}～{:.2f}，Y={:.2f}～{:.2f} mm）'.format(index, xmin, xmax, ymin, ymax))
    if rejected:
        raise ValueError('中心线模式不适用于实心圆、近圆形或紧凑块状区域：\n' +
                         '\n'.join(rejected) +
                         '\n已停止本次轨迹生成。请改用“实心排道填充”或“内外轮廓焊接”；混合图纸请先分开处理。')


def boundary_midlines(poly, spacing):
    """Direct equal-speed Euclidean wavefront collision approximation.

    Offset fronts meet at equal distance from their boundary sites. Solve
    those loci directly, rather than repeatedly buffering hundreds of layers.
    X/Y/diagonal sites use the same physical spacing and Euclidean metric;
    holes expand while exterior boundaries contract into the material.
    Boundary sampling is an approximation, not an exact segment Voronoi.
    """
    sites, sources = [], []
    rings = [poly.exterior, *poly.interiors]
    for ring_id, ring in enumerate(rings):
        coords = list(ring.coords)
        for edge_id, (a,b) in enumerate(zip(coords, coords[1:])):
            length = math.dist(a,b)
            if length < 1e-10:
                continue
            count = max(1, math.ceil(length/spacing))
            tangent = ((b[0]-a[0])/length, (b[1]-a[1])/length)
            for i in range(count):
                t = (i+0.5)/count
                sites.append((a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])))
                sources.append((ring_id, edge_id, a, b, tangent))
                if len(sites) > 30000:
                    raise ValueError('边界采样超过 30000 点，请调大中心线边界采样间距')
    if len(sites) < 4:
        raise ValueError('边界采样不足，请调小中心线采样间距')
    try:
        diagram = Voronoi(np.array(sites))
    except QhullError:
        raise ValueError('边界中线计算失败，请修复图形或调整边界采样间距')
    edges = []
    for (i,j), vertices in zip(diagram.ridge_points, diagram.ridge_vertices):
        if len(vertices) != 2 or -1 in vertices:
            continue
        first, second = sources[i], sources[j]
        if first[:2] == second[:2]:
            continue
        # Ignore cap/corner branches from two edges sharing a vertex.
        if first[0] == second[0] and any(math.dist(a,b) < 1e-8 for a in first[2:4] for b in second[2:4]):
            continue
        a,b = (tuple(diagram.vertices[k]) for k in vertices)
        if math.dist(a,b) < 1e-9:
            continue
        edges.append([a,b])
    # Batch the expensive geometric tests; no per-ridge GEOS object/dispatch.
    if edges:
        prepare(poly)
        keep=covers(poly,linestrings(np.asarray(edges)))
        edges=[edge for edge,accepted in zip(edges,keep) if accepted]
    # Contract degree-two chains, preserving exact junction coordinates.
    graph = nx.Graph()
    for a,b in edges:
        graph.add_edge(tuple(round(v,9) for v in a), tuple(round(v,9) for v in b))
    visited, chains = set(), []
    def edge(a,b):
        return frozenset((a,b))
    def trace(a,b):
        chain = [a,b]
        visited.add(edge(a,b))
        while graph.degree(chain[-1]) == 2 and chain[-1] != chain[0]:
            choices = [q for q in graph[chain[-1]] if edge(chain[-1],q) not in visited]
            if not choices:
                break
            q = choices[0]
            visited.add(edge(chain[-1],q))
            chain.append(q)
        chains.append(chain)
    for a in sorted(graph):
        if graph.degree(a) != 2:
            for b in sorted(graph[a]):
                if edge(a,b) not in visited:
                    trace(a,b)
    for a in sorted(graph):
        for b in sorted(graph[a]):
            if edge(a,b) not in visited:
                trace(a,b)
    # End caps advance at the same speed as all other boundary edges. Keep
    # their collision points; extending to the original edge undoes shrinking.
    return chains


def line_intersection(first, second):
    a,b = (np.array(v, dtype=float) for v in first)
    c,d = (np.array(v, dtype=float) for v in second)
    u,v = b-a,d-c
    cross = u[0]*v[1]-u[1]*v[0]
    if abs(cross) < 1e-10:
        return None
    w = c-a
    return tuple(a+u*((w[0]*v[1]-w[1]*v[0])/cross))


def clean_terminal_caps(paths, region, spacing):
    """Remove paired cap-corner spurs, freezing their inward collision point."""
    paths=[list(p) for p in paths]
    graph=nx.MultiGraph()
    for i,path in enumerate(paths):graph.add_edge(tuple(path[0]),tuple(path[-1]),key=i)
    removed=set()
    reach=math.hypot(region.bounds[2]-region.bounds[0],region.bounds[3]-region.bounds[1])*2
    def cap_hit(index,other):
        # Identify the *original* cap for classification only. Never insert
        # this boundary hit into the output: the endpoint stays contracted.
        path=paths[index]
        if tuple(path[-1])!=other:path=list(reversed(path))
        tip=np.array(other);direction=tip-np.array(path[max(0,len(path)-3)])
        length=np.linalg.norm(direction)
        if length<1e-10:return other
        hits=LineString([tuple(tip),tuple(tip+direction/length*reach)]).intersection(region.boundary)
        points=[(g.x,g.y) for g in getattr(hits,'geoms',[hits]) if g.geom_type=='Point']
        return min(points,key=lambda p:math.dist(p,other)) if points else other
    for node in graph:
        if graph.degree(node)!=3:continue
        ends=[]
        for a,b,key in graph.edges(node,keys=True):
            other=b if a==node else a
            if graph.degree(other)==1:ends.append((key,other))
        if len(ends)!=2:continue
        radius=region.boundary.distance(Point(node))
        if radius<=spacing or any(LineString(paths[k]).length>1.6*radius+spacing for k,_ in ends):continue
        a,b=(cap_hit(index,other) for index,other in ends)
        middle=Point((a[0]+b[0])/2,(a[1]+b[1])/2)
        if region.boundary.distance(middle)>max(spacing*1.5,radius*.05):continue
        removed.update(k for k,_ in ends)
    return [p for i,p in enumerate(paths) if i not in removed]


def single_ring_tail_junction(paths, region, spacing):
    """Contract the short medial bridge of a ring/diagonal-tail crossing.

    Requires one hole, one cycle, two opposite terminal tails and exactly two
    nearby degree-three vertices. All replacements stay in material; the loop
    and the full inner/outer tail must intersect at one point only.
    """
    if len(region.interiors)!=1:return paths
    graph=nx.Graph()
    for path in paths:
        for a,b in zip(path,path[1:]):
            a,b=tuple(a),tuple(b)
            if math.dist(a,b)>1e-9:graph.add_edge(a,b)
    if not nx.is_connected(graph):return paths
    terminals=[p for p in graph if graph.degree(p)==1]
    junctions=[p for p in graph if graph.degree(p)>2]
    cycles=nx.cycle_basis(graph)
    if len(terminals)!=2 or len(junctions)!=2 or len(cycles)!=1:return paths
    a,b=junctions
    if graph.degree(a)!=3 or graph.degree(b)!=3:return paths
    cycle=cycles[0]
    if a not in cycle or b not in cycle:return paths
    i=cycle.index(a);cycle=cycle[i:]+cycle[:i];j=cycle.index(b)
    arcs=[cycle[:j+1],[a]+list(reversed(cycle[j:]))]
    arcs.sort(key=lambda p:LineString(p).length)
    short,long=arcs
    radius=min(region.boundary.distance(Point(a)),region.boundary.distance(Point(b)))
    if LineString(short).length>1.25*radius+spacing or LineString(long).length<12*LineString(short).length:return paths
    cycle_edges={frozenset((x,y)) for x,y in zip(cycle,cycle[1:]+cycle[:1])}
    branches=graph.copy();branches.remove_edges_from([tuple(edge) for edge in cycle_edges])
    tails=[]
    for node in (a,b):
        found=[nx.shortest_path(branches,node,end) for end in terminals if nx.has_path(branches,node,end)]
        if len(found)!=1:return paths
        tails.append(found[0])
    u=np.array(tails[0][-1])-np.array(a);v=np.array(tails[1][-1])-np.array(b)
    # The ring junction can be wider than the contracted inner tail. Use the
    # tail's own local width; its valid end must not be extended to pass a
    # threshold measured in the wider ring material.
    for vector,tip in zip((u,v),(tails[0][-1],tails[1][-1])):
        if np.linalg.norm(vector)<max(spacing*2,region.boundary.distance(Point(tip))*.5):return paths
    if np.dot(u,v)/(np.linalg.norm(u)*np.linalg.norm(v))>-.85:return paths
    bridge=LineString(short);mid=bridge.interpolate(.5,normalized=True);joint=(mid.x,mid.y)
    loop=[joint]+long[1:-1]+[joint]
    inner=list(reversed(tails[0]))[:-1]
    outer=tails[1][1:]
    tail=inner+[joint]+outer
    # Preserve the already contracted inner/outer tail ends. No letter has
    # an exception that returns a terminal point to the original boundary.
    loop_line,tail_line=LineString(loop),LineString(tail)
    allowed=region.buffer(1e-7)
    if not all(allowed.covers(line) and line.is_simple for line in (loop_line,tail_line)):return paths
    intersection=loop_line.intersection(tail_line)
    if intersection.geom_type!='Point' or intersection.distance(Point(joint))>1e-6:return paths
    return [loop,tail]


def longest_run(path, tolerance):
    points = list(LineString(path).simplify(tolerance).coords)
    i = max(range(len(points)-1), key=lambda j: math.dist(points[j],points[j+1]))
    return points, i, math.dist(points[i],points[i+1])


def fit_contracted_terminal_stubs(paths,region,spacing):
    """Fit a short cap branch to its long stem at the offset cap, never at d=0.

    In an angular junction a collision stub can point towards a cap corner.
    Use a nearby long axis, and intersect it with that cap advanced by the
    same local radius as the side fronts. No glyph-name rules are involved.
    """
    paths=[list(p) for p in paths];graph=nx.MultiGraph()
    for i,p in enumerate(paths):graph.add_edge(tuple(p[0]),tuple(p[-1]),key=i)
    removed=set();reach=math.hypot(region.bounds[2]-region.bounds[0],region.bounds[3]-region.bounds[1])*2
    boundary_edges=[(a,b) for ring in (region.exterior,*region.interiors) for a,b in zip(list(ring.coords),list(ring.coords)[1:])]
    for node in graph:
        if graph.degree(node)<3:continue
        radius=region.boundary.distance(Point(node))
        if radius<spacing*2:continue
        incidents=list(graph.edges(node,keys=True))
        for a,b,index in incidents:
            tip=b if a==node else a
            if graph.degree(tip)!=1 or LineString(paths[index]).length>radius*2:continue
            supports=[]
            for _,_,other in incidents:
                if other==index:continue
                points,k,length=longest_run(paths[other],spacing*.25)
                if length<radius*3:continue
                p,q=map(np.array,points[k:k+2]);unit=(q-p)/length
                if LineString([tuple(p),tuple(q)]).distance(Point(node))>max(spacing,radius*.05):continue
                if np.dot(unit,np.array(tip)-node)<0:unit=-unit
                if np.dot(unit,np.array(tip)-node)<math.dist(tip,node)*.5:continue
                supports.append((length,unit,region.boundary.distance(Point((p+q)/2))))
            for _,unit,width_radius in sorted(supports,key=lambda item:item[0],reverse=True):
                r=min(radius,width_radius)
                ray=LineString([node,tuple(np.array(node)+unit*reach)])
                hits=ray.intersection(region.boundary)
                points=[(g.x,g.y) for g in getattr(hits,'geoms',[hits]) if g.geom_type=='Point']
                if not points:continue
                hit=min(points,key=lambda p:math.dist(node,p));candidate=None
                for p,q in boundary_edges:
                    length=math.dist(p,q)
                    if not r*.5<=length<=r*4 or LineString([p,q]).distance(Point(hit))>1e-6:continue
                    tangent=(np.array(q)-p)/length
                    speed=abs(tangent[0]*unit[1]-tangent[1]*unit[0])
                    if speed<.5:continue
                    target=tuple(np.array(hit)-unit*r/speed)
                    if np.dot(np.array(target)-node,unit)<-spacing:continue
                    line=LineString([node,target])
                    if math.dist(target,tip)>radius*2 or not region.buffer(-max(0,r-spacing*1.5)).covers(line):continue
                    candidate=target;break
                if candidate is None:continue
                if math.dist(node,candidate)<spacing:removed.add(index)
                else:paths[index]=[node,candidate]
                break
    return [p for i,p in enumerate(paths) if i not in removed]


def boundary_corner_supports(region, spacing):
    """Real angular vertices, with their adjoining straight boundary edges.

    A long pair of medial runs alone does not prove a sharp corner: rounded
    rectangles and U/C/S strokes also have long straight flanks. Smooth arc
    samples turn gradually and must not authorize replacing their medial arc.
    """
    corners=[];has_curves=False
    for ring in (region.exterior,*region.interiors):
        points=list(ring.coords)[:-1]
        for i,point in enumerate(points):
            left=np.asarray(points[i-1])-point
            right=np.asarray(points[(i+1)%len(points)])-point
            a,b=np.linalg.norm(left),np.linalg.norm(right)
            if min(a,b)<max(spacing*.05,1e-10):continue
            left,right=left/a,right/b
            # Opposite rays are a straight continuation. Ignore changes below
            # 25 degrees, including tangential straight/curve joins.
            cosine=np.dot(left,right)
            if cosine<-math.cos(math.radians(25)):
                if cosine>-1+1e-10:has_curves=True
                continue
            corners.append((np.asarray(point),((left,a),(right,b))))
    return corners,has_curves


def has_angular_boundary_support(corners,joint,first,second,radius,spacing):
    axes=[]
    for a,b in (first,second):
        direction=np.asarray(b)-a
        length=np.linalg.norm(direction)
        if length<1e-10:return False
        axes.append(direction/length)
    matched=[False,False]
    for point,edges in corners:
        if np.linalg.norm(point-joint)>max(radius*4,spacing*3):continue
        for direction,length in edges:
            if length<max(radius*1.5,spacing*3):continue
            for i,axis in enumerate(axes):
                if abs(np.dot(direction,axis))>.98:matched[i]=True
    # Separate corners joined by a short flat cap also support a real angular
    # crown (e.g. A); they need not be the same boundary vertex.
    return all(matched)


def centerline_encloses_holes(paths,region,tolerance=1e-7):
    if not region.interiors:return True
    faces=list(polygonize(unary_union([LineString(p) for p in paths if len(p)>1])))
    return all(any(face.buffer(tolerance).covers(Polygon(hole)) for face in faces)
               for hole in region.interiors)


def straighten_long_strokes(paths, region, spacing):
    """Preserve long straight supports; let shorter branches meet them.

    Replace medial-axis bends at a junction by the intersection of the dominant
    straight stroke and a transverse branch. Never move a long line to average
    it with a shorter one. All replacement segments must stay in material.
    """
    paths = [list(p) for p in paths]
    paths_before=[list(p) for p in paths]
    corners,has_curves = boundary_corner_supports(region,spacing)
    endpoints = {}
    for i,path in enumerate(paths):
        for side in (0,-1):
            endpoints.setdefault(tuple(path[side]),[]).append((i,side))
    allowed = region.buffer(1e-8)
    for junction, incidents in endpoints.items():
        if len(incidents) < 3:
            continue
        radius = region.boundary.distance(Point(junction))
        supports = []
        for index,side in incidents:
            if paths[index][0] == paths[index][-1]:
                continue
            oriented = paths[index] if side == 0 else list(reversed(paths[index]))
            pts = list(LineString(oriented).simplify(spacing*0.25).coords)
            lengths = [math.dist(a,b) for a,b in zip(pts,pts[1:])]
            # A single branch can contain two long sides (e.g. the arch of A).
            # Use the long support nearest this endpoint, not the global longest.
            threshold = max(max(lengths)*0.45, spacing*3)
            candidates = [i for i,length in enumerate(lengths) if length >= threshold]
            if not candidates:
                continue
            k = candidates[0]
            length = lengths[k]
            total = LineString(pts).length
            # A distant straight run across an entire loop is not a support
            # for this junction. Chopping that curved prefix erased R's bowl.
            prefix=LineString(pts[:k+1]).length if k else 0
            # Angular, simply-connected strokes (N/M) retain the established
            # long-run priority. Curved prefixes and bowls may not be chopped.
            if prefix>max(radius*2,spacing*3) and (has_curves or region.interiors):continue
            if length >= max(3*radius,spacing*3) or length >= (0.15 if not has_curves else 0.30)*total:
                supports.append((length,index,side,pts,k))
        if not has_curves:
            def keep_support(item):
                oriented=paths[item[1]] if item[2]==0 else list(reversed(paths[item[1]]))
                if len(endpoints.get(tuple(oriented[-1]),[]))!=1 or LineString(oriented).length>=radius*2:return True
                a,b=map(np.asarray,item[3][item[4]:item[4]+2]);u=(b-a)/np.linalg.norm(b-a)
                for other in supports:
                    if other[0]<radius*2:continue
                    c,d=map(np.asarray,other[3][other[4]:other[4]+2]);v=(d-c)/np.linalg.norm(d-c)
                    if abs(np.dot(u,v))>.98:return True
                return False
            supports=[item for item in supports if keep_support(item)]
        if len(supports) < 2:
            continue
        supports.sort(key=lambda item:item[0],reverse=True)
        primary = supports[0]
        axis = primary[3][primary[4]:primary[4]+2]
        a,b = map(np.array,axis)
        unit = (b-a)/np.linalg.norm(b-a)
        # Project onto the longest support first; the primary axis stays fixed.
        point = tuple(a+np.dot(np.array(junction)-a,unit)*unit)
        for other in supports[1:]:
            second = other[3][other[4]:other[4]+2]
            c,d = map(np.array,second)
            direction = (d-c)/np.linalg.norm(d-c)
            if abs(np.dot(direction,unit)) < 0.9:
                candidate = line_intersection(axis,second)
                if candidate is not None and math.dist(candidate,junction) <= max(3*radius,spacing*2):
                    point = candidate
                    break
        if math.dist(point,junction) > max(3*radius,spacing*2):
            continue
        # Real straight stroke intersections outrank cap-front collisions.
        # Smooth curves retain their equal-distance clearance; only source
        # angular edges can authorize this exception (no glyph-name rules).
        angular = any(has_angular_boundary_support(corners,np.asarray(point),axis,
                      item[3][item[4]:item[4]+2],radius,spacing)
                      for item in supports[1:]
                      if abs(np.dot((np.asarray(item[3][item[4]+1])-item[3][item[4]]) /
                                    item[0],unit)) < .9)
        clearance=min([radius]+[region.boundary.distance(Point(p))
                      for item in supports for p in item[3][item[4]:item[4]+2]])
        if (has_curves or not angular) and region.boundary.distance(Point(point))<clearance-spacing*1.5:
            continue
        if angular and not allowed.covers(Point(point)):
            # Some font stroke axes intersect beyond the flat crown. Keep the
            # dominant stem straight and use the inward cap as its fallback.
            vector=np.asarray(point)-junction
            forward=unit if np.dot(vector,unit)>0 else -unit
            ray=LineString([tuple(a-unit*1e5),tuple(a+unit*1e5)])
            section=ray.intersection(region)
            sections=[g for g in getattr(section,'geoms',[section]) if g.geom_type=='LineString' and g.distance(Point(junction))<radius*2]
            if not sections:continue
            section=min(sections,key=lambda g:g.distance(Point(junction)))
            cap=max(section.coords,key=lambda p:np.dot(np.asarray(p)-a,forward))
            point=tuple(np.asarray(cap)-forward*clearance)
        replacements = {}
        for index,side in incidents:
            oriented = paths[index] if side == 0 else list(reversed(paths[index]))
            support = next((item for item in supports if item[1:3] == (index,side)),None)
            if oriented[0] == oriented[-1]:
                updated = [point]+oriented[1:-1]+[point]
            elif support:
                pts,k = support[3],support[4]
                updated = [point]+pts[k+1:]
                v = np.array(pts[k+1])-np.array(pts[k])
                v /= np.linalg.norm(v)
                if k==len(pts)-2 and abs(np.dot(v,unit)) > 0.98 and len(endpoints.get(tuple(oriented[-1]),[]))==1:
                    # Fit the stem to the primary axis, preserving its inward
                    # endpoint level instead of extending back to the old cap.
                    terminal=tuple(a+np.dot(np.array(oriented[-1])-a,unit)*unit)
                    updated = [point,terminal]
            else:
                # A short cap-collision spur loses priority to a supported
                # straight intersection; do not turn it into a reverse hook.
                if angular and len(endpoints.get(tuple(oriented[-1]),[]))==1 and LineString(oriented).length<radius*2:
                    updated=[point,point]
                else:updated = [point]+oriented[1:]
            if LineString(updated).length>1e-8 and not allowed.covers(LineString(updated)):
                break
            replacements[index] = updated if side==0 else list(reversed(updated))
        else:
            for index,updated in replacements.items():
                paths[index] = updated
    # Within a bend, extend its two long straight runs to their intersection.
    result = []
    for path in paths:
        pts = list(LineString(path).simplify(spacing*0.25).coords)
        lengths = [math.dist(a,b) for a,b in zip(pts,pts[1:])]
        if len(lengths) > 2:
            threshold = max(max(lengths)*0.3,spacing*4)
            strong = [i for i,length in enumerate(lengths) if length >= threshold]
            edits = []
            for i,j in zip(strong,strong[1:]):
                if j <= i+1:
                    continue
                joint = line_intersection(pts[i:i+2],pts[j:j+2])
                if joint is None:
                    continue
                radius = region.boundary.distance(Point(pts[i+1]))
                if max(math.dist(joint,pts[i+1]), math.dist(joint,pts[j])) > max(4*radius,spacing*4):
                    continue
                if has_curves and not has_angular_boundary_support(corners,np.asarray(joint),pts[i:i+2],pts[j:j+2],radius,spacing):
                    continue
                clearance=min(region.boundary.distance(Point(pts[i+1])),region.boundary.distance(Point(pts[j])))
                angular=has_angular_boundary_support(corners,np.asarray(joint),pts[i:i+2],pts[j:j+2],radius,spacing)
                if (has_curves or not angular) and region.boundary.distance(Point(joint))<clearance-spacing*1.5:
                    continue
                replacement = LineString([pts[i],joint,pts[j+1]])
                if allowed.covers(replacement):
                    edits.append((i+1,j,[joint]))
                else:
                    # A's two dominant sloping axes may meet outside the solid.
                    # Keep both axes straight; replace the short rounded crown
                    # by a bridge at its existing medial height, not an unsafe apex.
                    middle = np.array(pts[i+1:j+1])
                    direction = np.array(joint)-middle.mean(axis=0)
                    norm = np.linalg.norm(direction)
                    if norm < 1e-10:
                        continue
                    direction /= norm
                    level = max(float(np.dot(v,direction)) for v in middle)
                    bridge = []
                    for a,b in ((pts[i],pts[i+1]),(pts[j],pts[j+1])):
                        a,b = np.array(a),np.array(b)
                        denominator = float(np.dot(b-a,direction))
                        if abs(denominator) < 1e-10:
                            break
                        bridge.append(tuple(a+(b-a)*(level-np.dot(a,direction))/denominator))
                    if len(bridge)==2 and allowed.covers(LineString([pts[i],*bridge,pts[j+1]])):
                        edits.append((i+1,j,bridge))
            for start,end,replacement in reversed(edits):
                pts[start:end+1] = replacement
        result.append(pts if allowed.covers(LineString(pts)) else path)
    # Straightening must keep every material hole surrounded by a weld loop.
    # Never accept a valid-in-material shortcut that loses the original bowl.
    result=[p for p in result if LineString(p).length>1e-8]
    return result if centerline_encloses_holes(result,region) else [list(p) for p in paths_before]


def straight_priority_trails(paths, region, tolerance, prune):
    # Pair collinear branches before considering lift count, so a long straight
    # stroke remains one weld pass even when a shorter trail cover is possible.
    graph = nx.MultiGraph()
    for i,p in enumerate(paths):
        if len(p)>1:
            graph.add_edge(tuple(p[0]),tuple(p[-1]),key=i,points=p,length=LineString(p).length)
    remove = [(a,b,k) for a,b,k,d in graph.edges(keys=True,data=True)
              if a!=b and d['length'] < prune and
              ((graph.degree(a)==1 and graph.degree(b)>2) or (graph.degree(b)==1 and graph.degree(a)>2))]
    graph.remove_edges_from(remove)
    pairs = {}
    for node in graph:
        ends = []
        for a,b,key,data in graph.edges(node,keys=True,data=True):
            p = data['points']
            for side in (0,-1):
                if tuple(p[side]) != node:
                    continue
                oriented = p if side==0 else list(reversed(p))
                # Direction from junction toward the long-run endpoint.
                q = np.array(oriented[1])-np.array(node)
                norm = np.linalg.norm(q)
                if norm>1e-10:
                    ends.append(((key,side),q/norm,data['length']))
        if len(ends) == 2:
            a,b = ends[0][0],ends[1][0]
            pairs[a]=b; pairs[b]=a
            continue
        candidates = []
        for i,first in enumerate(ends):
            for second in ends[i+1:]:
                dot = float(np.dot(first[1],second[1]))
                if dot < -0.94:
                    candidates.append((first[2]+second[2],-dot,first[0],second[0]))
        used = set()
        for _,_,a,b in sorted(candidates,reverse=True):
            if a not in used and b not in used:
                pairs[a]=b; pairs[b]=a; used.update((a,b))
    edge_data = {k:d['points'] for a,b,k,d in graph.edges(keys=True,data=True)}
    visited,result = set(),[]
    starts = [(k,side) for k in edge_data for side in (0,-1) if (k,side) not in pairs]
    starts.sort(key=lambda item:LineString(edge_data[item[0]]).length,reverse=True)
    for first in starts+[(k,0) for k in edge_data]:
        if first[0] in visited:
            continue
        current = first; points=[]
        while current[0] not in visited:
            k,side = current; visited.add(k)
            p = edge_data[k] if side==0 else list(reversed(edge_data[k]))
            points.extend(p if not points else p[1:])
            arriving = (k,-1 if side==0 else 0)
            if arriving not in pairs:
                break
            current = pairs[arriving]
        # Preserve shared junction vertices when simplifying. Otherwise a
        # nearly straight run can move off a crossbar endpoint and open a bowl.
        cuts=[0]+[i for i,p in enumerate(points[1:-1],1) if tuple(p) in graph and graph.degree(tuple(p))>2]+[len(points)-1]
        simplified_points=[]
        for first,last in zip(cuts,cuts[1:]):
            segment=LineString(points[first:last+1])
            simplified=segment.simplify(tolerance,preserve_topology=True)
            chosen=list(simplified.coords) if region.buffer(1e-8).covers(simplified) else points[first:last+1]
            simplified_points.extend(chosen if not simplified_points else chosen[1:])
        result.append(simplified_points)
    return sorted(result, key=lambda path: LineString(path).length, reverse=True)


def connected_weld_trails(paths):
    """Minimum edge-disjoint trails; join only actual shared intersections.

    Node the existing geometry, then cover each segment exactly once. Odd
    degree junctions require separate trails; no welding across a blank gap
    or retracing an already welded branch is introduced to force one pass.
    """
    graph=nx.Graph()
    for path in lines_of(unary_union([LineString(p) for p in paths if len(p)>1])):
        for a,b in zip(path,path[1:]):
            a,b=tuple(a),tuple(b)
            if math.dist(a,b)>1e-10:graph.add_edge(a,b)
    result=[]
    for nodes in nx.connected_components(graph):
        local=graph.subgraph(nodes).copy()
        odd=sorted(node for node in local if local.degree(node)%2)
        # Keep the established straight-priority routing when it already uses
        # the minimum pass count (e.g. a T must still use two passes).
        existing=[p for p in paths if len(p)>1 and tuple(p[0]) in nodes]
        real_length=sum(math.dist(a,b) for a,b in local.edges())
        if len(existing)==max(1,len(odd)//2) and abs(sum(LineString(p).length for p in existing)-real_length)<1e-6:
            result.extend(existing);continue
        if odd:
            hub=object()
            for node in odd:local.add_edge(hub,node)
            walk=nx.eulerian_circuit(local,source=hub)
        else:
            hub=None;walk=nx.eulerian_circuit(local,source=min(nodes))
        trail=[]
        for a,b in walk:
            if a is hub:
                trail=[b]
            elif b is hub:
                if len(trail)>1:result.append(trail)
                trail=[]
            else:
                if not trail:trail=[a]
                trail.append(b)
        if len(trail)>1:result.append(trail)
    return sorted(result,key=lambda path:LineString(path).length,reverse=True)


def center_paths(region, resolution, prune=0.5):
    # Immutable cached results cannot be changed by sorting/export callers.
    paths,notes=_cached_center_paths(region.wkb,resolution,prune)
    return [list(path) for path in paths],list(notes)


@lru_cache(maxsize=24)
def _cached_center_paths(region_wkb, resolution, prune):
    region=from_wkb(region_wkb)
    validate_centerline_region(region)
    paths = []
    for poly in polygons_of(region):
        local = boundary_midlines(poly, resolution)
        if not local:
            raise ValueError('未能匹配有效的相对边中线；请调整边界采样间距或改用填充 / 内外轮廓模式')
        # Collapse paired end-corner branches to their inward meeting point.
        # Applies to every stroke, not just Q. Scale the decision by local
        # half-width, so font height does not require a new mm cutoff.
        cleaned=clean_terminal_caps(local,poly,resolution)
        if centerline_encloses_holes(cleaned,poly):local=cleaned
        original=straighten_long_strokes(local,poly,resolution)
        original=fit_contracted_terminal_stubs(original,poly,resolution)
        if len(poly.interiors)==1:
            original=single_ring_tail_junction(original,poly,resolution)
        paths.extend(original)
    before = len(paths)
    paths = straight_priority_trails(paths, region, resolution*0.25, prune)
    paths = connected_weld_trails(paths)
    for poly in polygons_of(region):
        if poly.interiors:
            local=[p for p in paths if poly.buffer(1e-7).covers(LineString(p))]
            if not centerline_encloses_holes(local,poly):
                raise ValueError('中心线环结构不完整，已停止生成；请调整中心线采样间距并核对内孔，避免漏焊环线')
    notes=['中心线优先级：原边界支持的长直线交点优先，端面收缩交点其次；自由端仍等距收缩，移除干扰主笔画的端头短叉。曲线保持等距中线，所有替换须位于材料内并保留内孔。{} 个分支合并为 {} 条焊道，采样间距 {} mm，短分支阈值 {} mm。每段仅焊一次，不跨空白连接；复杂分叉仍需分道。'.format(before,len(paths),resolution,prune)]
    return tuple(tuple(tuple(point) for point in path) for path in paths),tuple(notes)


def plan_paths(paths, mode, width=2, overlap=20, angle=0, resolution=0.2, direction="从上向下", continuous=False, prune=0.5):
    if not all(math.isfinite(v) for v in (width, overlap, angle, resolution, prune)) or prune < 0 or width <= 0 or resolution <= 0 or not 0 <= overlap < 100:
        raise ValueError('焊缝宽度和中心线精度须大于 0，重叠率须在 0～100% 之间且不含 100%')
    region, warnings = solid_region(paths)
    if region.is_empty:
        raise ValueError('未找到有效封闭区域，无法生成实心加工轨迹')
    if mode == 'outline':
        result = boundary_paths(region)
    elif mode == 'fill':
        result, extra = fill_paths(region, width, overlap, angle, direction, continuous)
        warnings.extend(extra)
    elif mode == 'centerline':
        result, extra = center_paths(region, resolution, prune)
        warnings.extend(extra)
    else:
        raise ValueError('未知加工模式')
    if not result:
        raise ValueError('没有生成焊道，请减小焊缝宽度或中心线精度数值')
    return result, warnings


