import math


def discretize(points, step):
    if step <= 0:
        raise ValueError('离散步长必须大于 0')
    if not points:
        return []
    result = [tuple(points[0])]
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        if length < 1e-10:
            continue
        count = max(1, math.ceil(length / step))
        result.extend((a[0]+(b[0]-a[0])*i/count, a[1]+(b[1]-a[1])*i/count) for i in range(1, count+1))
    return result


def transform(point, origin, angle, scale):
    # CAD origin maps to user-frame (0, 0); rotate CAD axes into user axes.
    x, y = (point[0]-origin[0])*scale, (point[1]-origin[1])*scale
    r = math.radians(angle)
    return (x*math.cos(r)-y*math.sin(r), x*math.sin(r)+y*math.cos(r))


def program(paths, z, clearance, speed, arc_on, arc_off):
    if clearance <= z or speed <= 0:
        raise ValueError('安全高度必须高于作业高度，速度必须大于 0')
    lines = ['; GENERIC TEMPLATE - adapt and validate for your robot controller', '; Coordinates are relative to the robot user frame; distances in mm', '; Tool orientation, user frame and tool frame must be configured on controller']
    for index, path in enumerate(paths, 1):
        if len(path) < 2:
            continue
        x, y = path[0]
        lines.extend(['; contour {}'.format(index), arc_off,
                      'MOVE X={:.3f} Y={:.3f} Z={:.3f} V={:.3f}'.format(x, y, clearance, speed),
                      'MOVE X={:.3f} Y={:.3f} Z={:.3f} V={:.3f}'.format(x, y, z, speed), arc_on])
        for x, y in path[1:]:
            lines.append('MOVE X={:.3f} Y={:.3f} Z={:.3f} V={:.3f}'.format(x, y, z, speed))
        x, y = path[-1]
        lines.extend([arc_off, 'MOVE X={:.3f} Y={:.3f} Z={:.3f} V={:.3f}'.format(x, y, clearance, speed)])
    return '\n'.join(lines) + '\n'

def urscript(paths, z, clearance, speed, arc_output):
    if clearance <= z or speed <= 0 or not 0 <= arc_output <= 7:
        raise ValueError('检查高度、速度和数字输出编号（0～7）')
    lines = ['# Set user_frame and tool rotation before running; values below are placeholders',
             '# Dry-run with welding power disabled and verify all travel paths',
             'def cad_job():', '  user_frame = p[0,0,0,0,0,0]',
             '  tool_rx = 0.0', '  tool_ry = 0.0', '  tool_rz = 0.0',
             '  set_standard_digital_out(%d, False)' % arc_output]
    def move(point, height):
        return '  movel(pose_trans(user_frame, p[%.6f,%.6f,%.6f,tool_rx,tool_ry,tool_rz]), a=0.1, v=%.6f)' % (point[0]/1000, point[1]/1000, height/1000, speed/1000)
    for index, path in enumerate(paths, 1):
        if len(path) < 2:
            continue
        lines.extend(['  # Seam %d: travel above start, then descend with arc off' % index,
                      move(path[0], clearance), move(path[0], z), '  set_standard_digital_out(%d, True)' % arc_output])
        lines.extend(move(point, z) for point in path[1:])
        lines.extend(['  set_standard_digital_out(%d, False)' % arc_output,
                      '  # Lift %.3f mm along user Z at seam end before any XY travel' % (clearance-z),
                      move(path[-1], clearance)])
    lines.extend(['  set_standard_digital_out(%d, False)' % arc_output, 'end'])
    return '\n'.join(lines) + '\n'
