"""UR and ELITE CS/ES script adapters. No network activity on import/export."""
from dataclasses import dataclass, asdict
import ipaddress
import keyword
import json
import math
import re
import socket
from pathlib import Path
from runtime_paths import CONFIG_FILE

DEFAULT_BRAND = 'ELITE CS/ES'
BRANDS = {'ELITE CS/ES': {'port':30001,'max_do':15,'pose':'XYZ 欧拉角 Rx/Ry/Rz（rad）'},
          'UR': {'port':30002,'max_do':7,'pose':'旋转向量 Rx/Ry/Rz（rad）'}}
PROFILE_FILE = CONFIG_FILE

@dataclass
class RobotConfig:
    brand: str = DEFAULT_BRAND
    model: str = ''
    version: str = ''
    host: str = ''
    port: int = 30001
    dashboard_port: int = 29999
    state_port: int = 30011
    name: str = 'cad_job'
    frame: tuple = (0,0,0,0,0,0)
    tcp: tuple = (0,0,0,0,0,0)
    orientation: tuple = (0,0,0)
    tcp_mode: str = 'controller'
    orientation_mode: str = 'current'
    travel_speed: float = 30.0
    acceleration: float = 100.0
    blend_radius: float = 0.0
    output: int = 0
    active_high: bool = True
    weld_enabled: bool = False
    ignition_wait: float = 0.0
    end_wait: float = 0.0
    verified: bool = False

    def validate(self, network=False):
        if self.tcp_mode not in ('controller','configured') or self.orientation_mode not in ('current','base','user'):
            raise ValueError('TCP 或姿态参考模式无效')
        if self.brand not in BRANDS:
            raise ValueError('仅支持 UR 和 ELITE CS/ES；不适用于 ELITE EC/EA')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', self.name) or keyword.iskeyword(self.name) or self.name in {'thread','sec','sync','run','halt','def','end','if','while','for','True','False','sleep','movel','pose_trans','set_tcp'}:
            raise ValueError('程序名须以英文字母开头，只含字母、数字、下划线，不能使用脚本关键字')
        for key,size in [('frame',6),('tcp',6),('orientation',3)]:
            values=getattr(self,key)
            if len(values)!=size or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):
                raise ValueError(key+' 的数值数量或格式错误')
        for value in (self.travel_speed,self.acceleration,self.blend_radius,self.ignition_wait,self.end_wait):
            if not math.isfinite(value):
                raise ValueError('机器人参数必须为有限数值')
        if self.blend_radius<0:
            raise ValueError('圆滑半径不能小于 0；0 表示精确停点')
        if self.travel_speed<=0 or self.acceleration<=0 or min(self.ignition_wait,self.end_wait)<0:
            raise ValueError('速度、加速度须大于 0；等待时间不能小于 0')
        if isinstance(self.output,bool) or not isinstance(self.output,int) or not 0<=self.output<=BRANDS[self.brand]['max_do']:
            raise ValueError('当前机器人标准 DO 编号范围为 0～'+str(BRANDS[self.brand]['max_do']))
        for port in (self.port,self.dashboard_port,self.state_port):
            if isinstance(port,bool) or not isinstance(port,int) or not 1<=port<=65535:
                raise ValueError('端口必须为 1～65535 的整数')
        if not all(isinstance(v,bool) for v in (self.active_high,self.weld_enabled,self.verified)):
            raise ValueError('输出使能和确认选项须为布尔值')
        if network:
            try: ipaddress.ip_address(self.host)
            except ValueError: raise ValueError('请输入机器人 IPv4/IPv6 地址')


def defaults(brand):
    return RobotConfig(brand=brand,port=BRANDS[brand]['port'])


def load_profiles(path=PROFILE_FILE):
    configs={brand:defaults(brand) for brand in BRANDS}
    if Path(path).exists():
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        for brand,values in data.items():
            if brand in configs:
                c=RobotConfig(**values)
                if c.brand!=brand: raise ValueError('配置品牌不一致')
                c.validate()
                c.verified=False
                configs[brand]=c
    return configs


def save_profiles(configs,path=PROFILE_FILE):
    for c in configs.values(): c.validate()
    path=Path(path)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({k:{**asdict(v),'verified':False} for k,v in configs.items()},ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def blend_radii(path,requested):
    """Millimetre blend-zone radii, capped below half of either adjacent leg.

    Only internal weld vertices blend. Endpoints, zero-length legs and near
    reversals stop exactly. This is a geometric guard, not robot simulation.
    """
    radii=[0.0]*len(path)
    for i in range(1,len(path)-1):
        a,b,c=path[i-1:i+2]
        incoming=(b[0]-a[0],b[1]-a[1])
        outgoing=(c[0]-b[0],c[1]-b[1])
        left,right=math.hypot(*incoming),math.hypot(*outgoing)
        if min(left,right)<1e-9:
            continue
        cosine=sum(x*y for x,y in zip(incoming,outgoing))/(left*right)
        if cosine < -0.95:
            continue
        radii[i]=min(requested,0.45*left,0.45*right)
    return radii


def render_script(paths,z,clearance,speed,c):
    c.validate()
    if not all(math.isfinite(v) for v in (z,clearance,speed)) or clearance<=z or speed<=0:
        raise ValueError('作业速度须大于 0，过渡高度须高于作业 Z')
    paths=[list(p) for p in paths if len(p)>=2]
    if not paths: raise ValueError('没有可导出的焊道')
    if not all(len(p)==2 and all(math.isfinite(v) for v in p) for path in paths for p in path):
        raise ValueError('轨迹点必须为有限的 XY 数值')
    elite=c.brand=='ELITE CS/ES'
    def pose(values):
        return ('' if elite else 'p')+'['+','.join('%.9f'%v for v in values)+']'
    def converted(values):
        return [v/1000 if i<3 else v for i,v in enumerate(values)]
    lines=['# CAD welding program / '+c.brand,
           '# Orientation: '+('XYZ Euler radians' if elite else 'rotation vector radians'),
           '# Simulation and calibrated frame/TCP required before hardware use',
           '# Digital arc control only; welding handshake is not implemented',
           'def '+c.name+'():',
           '  user_frame = '+pose(converted(c.frame))]
    if c.tcp_mode=='configured':
        lines.append('  set_tcp('+pose(converted(c.tcp))+')')
    else:
        lines.append('  # Retain the calibrated TCP selected on the controller')
    lines.append('  # Orientation reference: '+c.orientation_mode)
    if c.orientation_mode=='current':
        lines.append('  start_pose = get_actual_tcp_pose()')
    def arc(on):
        if c.weld_enabled:
            state=c.active_high if on else not c.active_high
            lines.append('  set_standard_digital_out(%d, %s)'%(c.output,str(state)))
        else:
            lines.append('  # DRY RUN: arc '+('ON' if on else 'OFF')+' omitted; no welding DO changes')
    def move(p,height,v,radius=0):
        target=pose([p[0]/1000,p[1]/1000,height/1000,*(c.orientation if c.orientation_mode=='user' else (0,0,0))])
        if c.orientation_mode=='user':
            expression='pose_trans(user_frame, %s)'%target
        else:
            lines.append('  target_pose = pose_trans(user_frame, %s)'%target)
            attitude=','.join('start_pose[%d]'%i for i in (3,4,5)) if c.orientation_mode=='current' else ','.join('%.9f'%v for v in c.orientation)
            expression=('' if elite else 'p')+'[target_pose[0],target_pose[1],target_pose[2],'+attitude+']'
        radius_text='%.9f'%(radius/1000) if radius>0 else '0'
        lines.append('  movel(%s, a=%.9f, v=%.9f, r=%s)'%(expression,c.acceleration/1000,v/1000,radius_text))
    arc(False)
    for index,path in enumerate(paths,1):
        radii=blend_radii(path,c.blend_radius)
        limited=sum(1 for i in range(1,len(path)-1) if radii[i]<c.blend_radius)
        lines.append('  # Seam %d; requested blend %.6f mm; limited internal vertices %d'%(index,c.blend_radius,limited))
        move(path[0],clearance,c.travel_speed)
        move(path[0],z,c.travel_speed)
        arc(True)
        if c.weld_enabled and c.ignition_wait: lines.append('  sleep(%.6f)'%c.ignition_wait)
        for i,p in enumerate(path[1:],1): move(p,z,speed,radii[i])
        if c.weld_enabled and c.end_wait: lines.append('  sleep(%.6f)'%c.end_wait)
        arc(False)
        move(path[-1],clearance,c.travel_speed)
    arc(False)
    lines.append('end')
    return '\n'.join(lines)+'\n'


def test_connection(c,timeout=3):
    from robot_control import connection_report,connection_text
    return connection_text(connection_report(c,timeout))


def send_script(c,script,timeout=5):
    c.validate(network=True)
    if not c.verified: raise ValueError('发送前请确认该配置及轨迹已验证')
    if not script.startswith('# CAD welding program / '+c.brand+'\n') or ('def '+c.name+'():\n') not in script or not script.endswith('\nend\n'):
        raise ValueError('脚本与当前品牌或程序名不一致，请重新生成')
    # ELITE Primary treats comments outside a def as RPC commands and reports
    # "No '#' command". Keep annotated exports, but send a clean program.
    wire=script if c.brand=='UR' else '\n'.join(line for line in script.splitlines() if line.strip() and not line.lstrip().startswith('#'))+'\n'
    payload=wire.encode('utf-8')
    if len(payload)>8*1024*1024: raise ValueError('脚本超过 8 MB，请增大离散步长或分图处理')
    with socket.create_connection((c.host,c.port),timeout=timeout) as client:
        client.settimeout(timeout)
        client.sendall(payload)
    return '已发送 %d 字节；控制器可能立即执行。尚未确认加载、运行或完成状态。'%len(payload)
