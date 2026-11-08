"""Dashboard controls plus primary read-only feedback. No automatic power-on."""
import socket
import struct
import time
import threading
import math
from dataclasses import replace
from robot_adapters import send_script


def recv_exact(sock,count):
    data=b''
    while len(data)<count:
        chunk=sock.recv(count-len(data))
        if not chunk:raise ConnectionError('机器人状态连接已关闭')
        data+=chunk
    return data


def parse_state(packet):
    if len(packet)<5 or packet[4]!=16:return None
    result={};offset=5
    while offset<len(packet):
        if offset+5>len(packet):raise ValueError('状态子包头不完整')
        size,kind=struct.unpack_from('>IB',packet,offset)
        if size<5 or offset+size>len(packet):raise ValueError('状态子包长度错误')
        if kind==0 and size>=21:
            result.update(power=bool(packet[offset+15]),emergency=bool(packet[offset+16]),
                          protective=bool(packet[offset+17]),mode=packet[offset+20],
                          state='PAUSED' if packet[offset+19] else ('RUNNING' if packet[offset+18] else 'STOPPED'))
        elif kind==3 and size>=13:
            result['outputs']=struct.unpack_from('>I',packet,offset+9)[0]
        elif kind==4:
            if size<101:raise ValueError('笛卡尔位姿子包不完整')
            values=struct.unpack_from('>12d',packet,offset+5)
            if not all(math.isfinite(v) for v in values):raise ValueError('控制器返回了无效 TCP 位姿')
            result['tcp_pose']=values[:6]
            result['tcp_offset']=values[6:]
        offset+=size
    return result if 'state' in result else None


def read_state(config,timeout=2,required=('state',)):
    config.validate(network=True)
    deadline=time.monotonic()+timeout
    with socket.create_connection((config.host,config.state_port),timeout=timeout) as sock:
        while time.monotonic()<deadline:
            sock.settimeout(max(.01,deadline-time.monotonic()))
            size=struct.unpack('>I',recv_exact(sock,4))[0]
            if not 5<=size<=1024*1024:raise ValueError('机器人状态包长度不合法')
            state=parse_state(struct.pack('>I',size)+recv_exact(sock,size-4))
            if state is not None and all(key in state for key in required):return state
    raise TimeoutError('未收到机器人运行状态')


def read_teaching_sample(config):
    """Only receive Primary data; never send a script, set TCP, or move."""
    from frame_teaching import same_tcp
    first=read_state(config,required=('state','tcp_pose','tcp_offset'))
    time.sleep(.12)
    second=read_state(config,required=('state','tcp_pose','tcp_offset'))
    def mm(pose):return tuple(v*1000 if i<3 else v for i,v in enumerate(pose))
    for state in (first,second):
        if state['state']!='STOPPED':raise ValueError('机器人程序未停止，不能记录示教点')
        if state['emergency'] or state['protective']:raise ValueError('控制器处于安全停止状态，不能记录示教点')
    left,right=mm(first['tcp_pose']),mm(second['tcp_pose'])
    if math.dist(left[:3],right[:3])>.1:
        raise ValueError('TCP 正在移动，请在示教器停稳后再次记录')
    offset=mm(second['tcp_offset'])
    if not same_tcp(mm(first['tcp_offset']),offset,config.brand):
        raise ValueError('采样期间 TCP 配置发生变化，请重新记录')
    if config.tcp_mode=='configured' and not same_tcp(config.tcp,offset,config.brand):
        raise ValueError('控制器当前 TCP 与软件设置不一致，请先在示教器选用同一 TCP 再示教')
    return right[:3],offset


def connection_report(config,timeout=1):
    """Probe each interface independently; never sends motion or changes mode."""
    config.validate(network=True)
    result={'brand':config.brand,'host':config.host,'interfaces':{},'state':None,'remote':None}
    interfaces=result['interfaces']
    try:
        with socket.create_connection((config.host,config.port),timeout=timeout):pass
        interfaces['脚本']={'port':config.port,'ok':True}
    except OSError as exc:interfaces['脚本']={'port':config.port,'ok':False,'error':str(exc)}
    try:
        result['state']=read_state(config,timeout=timeout)
        interfaces['状态']={'port':config.state_port,'ok':True}
    except (OSError,ValueError) as exc:interfaces['状态']={'port':config.state_port,'ok':False,'error':str(exc)}
    try:
        result['remote']=dashboard(config,'remoteControl -s' if config.brand=='ELITE CS/ES' else 'is in remote control',timeout=timeout)
        interfaces['控制']={'port':config.dashboard_port,'ok':True}
    except (OSError,ValueError,RuntimeError) as exc:interfaces['控制']={'port':config.dashboard_port,'ok':False,'error':str(exc)}
    result['connected']=all(item['ok'] for item in interfaces.values())
    result['remote_ready']=str(result['remote']).strip().lower() in ('remote','true')
    return result


def connection_text(report):
    interfaces=report['interfaces']
    endpoints=' · '.join('{} {} {}'.format(name,item['port'],'✓' if item['ok'] else '失败') for name,item in interfaces.items())
    prefix='已连接' if report['connected'] else ('部分连接' if any(i['ok'] for i in interfaces.values()) else '未连接')
    mode=('远程' if report['remote_ready'] else '非远程 / 未确认')
    state=report.get('state')
    ready=''
    if state:
        ready=' · '+('安全停止' if state['emergency'] or state['protective'] else ('已上电' if state['power'] else '未上电'))
        ready+=' · '+{'RUNNING':'运行中','PAUSED':'已暂停','STOPPED':'已停止'}[state['state']]
    return '{} · {} {}\n{} · {}{}'.format(prefix,report['brand'],report['host'],endpoints,mode,ready)


def dashboard(config,command,timeout=2):
    if command not in ('pause','stop','play','remoteControl -s','is in remote control'):
        raise ValueError('不支持的运行控制命令')
    config.validate(network=True)
    with socket.create_connection((config.host,config.dashboard_port),timeout=timeout) as sock:
        # ELITE sends a multiline banner; drain it before reading the reply.
        sock.settimeout(.15);banner=b''
        while len(banner)<8192:
            try:
                chunk=sock.recv(4096)
                if not chunk:raise ConnectionError('Dashboard 已断开')
                banner+=chunk
            except socket.timeout:break
        sock.settimeout(timeout);sock.sendall((command+'\n').encode('ascii'))
        answer=b''
        while len(answer)<8192:
            chunk=sock.recv(4096)
            if not chunk:break
            answer+=chunk
            if b'\n' in answer:break
        text=answer.decode('utf-8',errors='replace').strip()
        if not text:raise ConnectionError('Dashboard 未返回结果；不会自动重发')
        if command in ('pause','stop','play'):
            expected={'pause':('pausing',),'stop':('stopped','stopping'),'play':('starting',)}[command]
            if not text.lower().startswith(expected):raise RuntimeError(text)
        return text


def arc_output(config,on):
    if not config.weld_enabled:return
    value=config.active_high if on else not config.active_high
    script='sec cad_arc_control():\n  set_standard_digital_out(%d, %s)\nend\n'%(config.output,value)
    with socket.create_connection((config.host,config.port),timeout=2) as sock:
        sock.settimeout(2);sock.sendall(script.encode('ascii'))
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        state=read_state(config)
        if 'outputs' in state and bool(state['outputs']&(1<<config.output))==value:return
        time.sleep(.05)
    raise RuntimeError('未确认起熄弧 DO 状态，请检查控制器')


class RobotRunner:
    def __init__(self):
        self.config=None
        self.state='IDLE'
        self.arc_was_on=None
        self.cancel=threading.Event()
        self.lock=threading.RLock()

    def wait_state(self,expected,timeout=3):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            current=read_state(self.config)
            if current['state']==expected:return current
            if self.cancel.is_set() and expected!='STOPPED':raise RuntimeError('停止请求已接收')
            time.sleep(.05)
        raise RuntimeError('控制器未确认状态 '+expected+'；不会重新发送轨迹')

    def start(self,config,script):
        with self.lock:
            if self.cancel.is_set():raise RuntimeError('启动已取消')
            self.config=replace(config,verified=True)
            state=read_state(self.config)
            if state['state']!='STOPPED':raise ValueError('控制器当前正在运行或暂停，请先停止；不会覆盖现有任务')
            if not state['power'] or state['emergency'] or state['protective']:
                raise ValueError('机器人未就绪，请在控制器完成上电及安全检查')
            query='remoteControl -s' if config.brand=='ELITE CS/ES' else 'is in remote control'
            remote=dashboard(self.config,query).strip().lower()
            if remote not in ('remote','true'):raise ValueError('机器人未处于远程控制模式')
            if self.cancel.is_set():raise RuntimeError('启动已取消')
            self.state='UNKNOWN'
            send_script(self.config,script)
            self.wait_state('RUNNING')
            self.state='RUNNING'
            return '运行中'

    def pause(self):
        with self.lock:
            if self.config is None:raise ValueError('当前没有本软件启动的任务')
            dashboard(self.config,'pause')
            state=self.wait_state('PAUSED')
            self.state='PAUSED_UNCONFIRMED';self.arc_was_on=None
            try:
                if self.config.weld_enabled:
                    if 'outputs' not in state:raise RuntimeError('未读取到起弧输出状态')
                    self.arc_was_on=bool(state['outputs']&(1<<self.config.output))==self.config.active_high
            finally:
                arc_output(self.config,False)
            self.state='PAUSED'
            return '已暂停，起弧输出已关闭' if self.config.weld_enabled else '已暂停'

    def resume(self):
        with self.lock:
            if self.state!='PAUSED':raise ValueError('任务未处于已确认暂停状态，不能继续')
            if self.config.brand=='UR':
                raise ValueError('本版不对 UR 外部脚本自动续跑，请停止后重新启动；暂停已关闭的起弧输出不会由示教器继续按钮自动恢复')
            if read_state(self.config)['state']!='PAUSED':raise ValueError('控制器已不在暂停状态，请先停止后重新启动')
            try:
                if self.cancel.is_set():raise RuntimeError('继续已取消')
                if self.arc_was_on:
                    arc_output(self.config,True)
                    if self.cancel.wait(self.config.ignition_wait):raise RuntimeError('继续已取消')
                if self.cancel.is_set():raise RuntimeError('继续已取消')
                dashboard(self.config,'play');self.wait_state('RUNNING')
            except Exception:
                arc_output(self.config,False)
                raise
            self.state='RUNNING';return '已继续原任务'

    def stop(self,config=None):
        self.cancel.set()
        with self.lock:
            if self.config is None:
                if config is None:raise ValueError('请先配置机器人 IP')
                self.config=replace(config)
            error=None
            try:
                dashboard(self.config,'stop');self.wait_state('STOPPED')
            except Exception as exc:error=exc
            finally:
                arc_output(self.config,False)
            if error:raise error
            self.state='STOPPED';self.arc_was_on=None
            return '已停止；再次启动将从头执行'

    def refresh(self):
        if self.config is None:return None
        return read_state(self.config)
