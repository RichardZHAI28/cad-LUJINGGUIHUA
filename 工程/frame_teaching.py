"""Right-handed workpiece frame from three base-frame TCP positions (mm)."""
import math
import warnings
import numpy as np
from scipy.spatial.transform import Rotation


def project_axis(vector,scale=1):
    """Orthographic camera on the +X,+Y,+Z side; screen Y points down.

    Screen right is (-1,1,0)/sqrt(2); screen up is (-1,-1,2)/sqrt(6).
    right cross up = camera-to-viewer normal (1,1,1)/sqrt(3).
    """
    x,y,z=vector
    return scale*(y-x)/math.sqrt(2),scale*(x+y-2*z)/math.sqrt(6)


def frame_rotation(frame, brand):
    if brand == 'UR':return Rotation.from_rotvec(frame[3:])
    if brand == 'ELITE CS/ES':return Rotation.from_euler('xyz',frame[3:])
    raise ValueError('不支持的机器人品牌')


def teach_frame(points, brand):
    values=np.asarray(points,dtype=float)
    if values.shape != (3,3) or not np.isfinite(values).all():
        raise ValueError('三点必须各包含基座坐标 X、Y、Z 三个有限数值，单位 mm')
    origin,px,py=values
    vx,vy=px-origin,py-origin
    lx,ly=np.linalg.norm(vx),np.linalg.norm(vy)
    if min(lx,ly)<1:
        raise ValueError('方向点距原点不足 1 mm，请增大示教点间距')
    ux=vx/lx
    normal=np.cross(ux,vy)
    altitude=np.linalg.norm(normal)
    sine=altitude/ly
    if altitude<1 or sine<math.sin(math.radians(5)):
        raise ValueError('三点共线或过于接近共线；请将第三点移到 X 轴的 Y 正侧，垂距至少 1 mm、夹角至少 5°')
    uz=normal/altitude
    uy=np.cross(uz,ux)
    matrix=np.column_stack((ux,uy,uz))
    rotation=Rotation.from_matrix(matrix)
    if brand == 'UR':angles=rotation.as_rotvec()
    elif brand == 'ELITE CS/ES':
        # Matches Elite's official SDK: R = Rz(rz) * Ry(ry) * Rx(rx).
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            angles=rotation.as_euler('xyz')
    else:raise ValueError('不支持的机器人品牌')
    frame=tuple(float(v) for v in (*origin,*angles))
    return frame, {'x':tuple(ux),'y':tuple(uy),'z':tuple(uz),
                   'x_distance':float(lx),'plane_distance':float(altitude)}


def same_tcp(left,right,brand):
    return (np.linalg.norm(np.asarray(left[:3])-right[:3]) <= .01
            and (frame_rotation(left,brand).inv()*frame_rotation(right,brand)).magnitude() <= .001)
