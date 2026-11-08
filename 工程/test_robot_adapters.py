import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.vendor'))
import tempfile
import unittest
import socket
import threading
import re
from unittest.mock import patch, MagicMock
from dataclasses import replace
from robot_adapters import *

PATHS=[[(100,200),(110,200)],[(120,210),(130,210)]]

class RobotAdaptersTests(unittest.TestCase):
    def test_blend_only_inside_seam_and_mm_to_m(self):
        path=[(0,0),(10,0),(10,10),(20,10)]
        for brand in BRANDS:
            c=replace(defaults(brand),blend_radius=2,weld_enabled=True)
            s=render_script([path,path],0,20,10,c)
            moves=[line for line in s.splitlines() if 'movel(' in line]
            radii=[float(re.search(r'r=([0-9.]+)',line).group(1)) for line in moves]
            self.assertEqual(radii,[0,0,.002,.002,0,0]*2)

    def test_blend_short_segment_limit_and_reversal(self):
        path=[(0,0),(10,0),(10,1),(20,1)]
        radii=blend_radii(path,20)
        self.assertEqual(radii,[0,.45,.45,0])
        for i in range(len(path)-1):
            self.assertLess(radii[i]+radii[i+1],math.dist(path[i],path[i+1]))
        self.assertEqual(blend_radii([(0,0),(10,0),(0,0)],2),[0,0,0])
        self.assertEqual(blend_radii([(0,0),(0,0),(10,0)],2),[0,0,0])
        with self.assertRaises(ValueError):replace(defaults('UR'),blend_radius=-1).validate()
        with self.assertRaises(ValueError):replace(defaults('UR'),blend_radius=float('nan')).validate()

    def test_old_profile_without_blend_loads_zero_and_new_value_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json'
            data=asdict(defaults('UR'));data.pop('blend_radius')
            path.write_text(json.dumps({'UR':data}),encoding='utf-8')
            restored=load_profiles(path)
            self.assertEqual(restored['UR'].blend_radius,0)
            restored['ELITE CS/ES'].blend_radius=1.5
            save_profiles(restored,path)
            self.assertEqual(load_profiles(path)['ELITE CS/ES'].blend_radius,1.5)

    def test_real_loopback_transmits_complete_script(self):
        for brand in BRANDS:
            received=[]
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
                server.bind(('127.0.0.1',0));server.listen(1);server.settimeout(3)
                def receive():
                    with server.accept()[0] as client:
                        client.settimeout(3)
                        chunks=[]
                        while True:
                            chunk=client.recv(4096)
                            if not chunk:break
                            chunks.append(chunk)
                        received.append(b''.join(chunks))
                worker=threading.Thread(target=receive,daemon=True);worker.start()
                c=replace(defaults(brand),host='127.0.0.1',port=server.getsockname()[1],verified=True)
                script=render_script(PATHS,0,20,10,c)
                send_script(c,script)
                worker.join(4)
                self.assertFalse(worker.is_alive())
                expected=script if brand=='UR' else '\n'.join(line for line in script.splitlines() if line.strip() and not line.lstrip().startswith('#'))+'\n'
                self.assertEqual(received,[expected.encode('utf-8')])
                if brand=='ELITE CS/ES':self.assertTrue(received[0].startswith(b'def '));self.assertNotIn(b'#',received[0])

    def test_native_pose_types_and_units(self):
        for brand in BRANDS:
            c=replace(defaults(brand),frame=(100,200,300,.1,.2,.3),tcp=(0,0,100,.4,.5,.6),orientation=(.7,.8,.9),tcp_mode='configured',orientation_mode='user')
            s=render_script(PATHS,5,25,10,c)
            prefix='p' if brand=='UR' else ''
            self.assertIn('user_frame = '+prefix+'[0.100000000,0.200000000,0.300000000,0.100000000,0.200000000,0.300000000]',s)
            self.assertIn('set_tcp('+prefix+'[0.000000000,0.000000000,0.100000000',s)
            self.assertIn('0.700000000,0.800000000,0.900000000',s)
            self.assertIn('v=0.010000000',s)
            self.assertTrue(s.endswith('\nend\n'))
            self.assertNotIn('set_standard_digital_out(',s)
            if brand!='UR':self.assertNotIn('p[',s)

    def test_current_and_base_attitudes_do_not_rotate_with_user_frame(self):
        for mode in ('current','base','user'):
            c=replace(defaults('ELITE CS/ES'),frame=(500,400,400,0,0,math.pi/2),orientation=(.2,.3,.4),orientation_mode=mode)
            script=render_script([[(10,0),(20,0)]],0,10,10,c)
            actual=[.5,.4,.4,-1.0,.1,.8];moves=[];reads=[]
            def compose(a,b):
                # This fixture rotates only about Z; zero local rotation for current/base.
                return [a[0]-b[1],a[1]+b[0],a[2]+b[2],b[3],b[4],a[5]+b[5]]
            def read():reads.append(True);return actual[:]
            scope={'pose_trans':compose,'get_actual_tcp_pose':read,'movel':lambda p,**kw:moves.append(p)}
            exec(script.rsplit('\nend',1)[0],scope)
            scope[c.name]()
            self.assertAlmostEqual(moves[0][0],.5)
            self.assertAlmostEqual(moves[0][1],.41)
            self.assertAlmostEqual(moves[0][2],.41)
            expected=actual[3:] if mode=='current' else ([.2,.3,.4] if mode=='base' else [.2,.3,math.pi/2+.4])
            for move in moves:
                for got,want in zip(move[3:],expected):self.assertAlmostEqual(got,want,places=8)
            self.assertEqual(len(reads),1 if mode=='current' else 0)
            self.assertNotIn('set_tcp(',script)

    def test_legacy_profile_defaults_preserve_controller_tcp_and_attitude(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.json'
            data=asdict(defaults('ELITE CS/ES'))
            data.pop('tcp_mode');data.pop('orientation_mode')
            path.write_text(json.dumps({'ELITE CS/ES':data}),encoding='utf-8')
            c=load_profiles(path)['ELITE CS/ES']
            self.assertEqual((c.tcp_mode,c.orientation_mode),('controller','current'))
        for changes in ({'tcp_mode':'invalid'},{'orientation_mode':'invalid'}):
            with self.assertRaises(ValueError):replace(c,**changes).validate()

    def test_brand_do_bounds_and_arc_polarity(self):
        elite=replace(defaults('ELITE CS/ES'),output=15,weld_enabled=True,active_high=False,ignition_wait=.3,end_wait=.2)
        s=render_script(PATHS,5,25,10,elite)
        self.assertEqual(s.count('set_standard_digital_out(15, False)'),2)
        self.assertIn('sleep(0.300000)',s)
        with self.assertRaises(ValueError):replace(elite,brand='UR').validate()
        with self.assertRaises(ValueError):replace(elite,output=16).validate()

    def test_lift_transfer_before_next_ignition(self):
        for brand in BRANDS:
            c=replace(defaults(brand),weld_enabled=True)
            s=render_script(PATHS,5,25,10,c)
            on=s.index('set_standard_digital_out(0, True)')
            off=s.index('set_standard_digital_out(0, False)',on)
            lift=s.index('0.110000000,0.200000000,0.025000000',off)
            transfer=s.index('0.120000000,0.210000000,0.025000000',lift)
            descent=s.index('0.120000000,0.210000000,0.005000000',transfer)
            next_on=s.index('set_standard_digital_out(0, True)',descent)
            self.assertLess(off,lift);self.assertLess(lift,transfer);self.assertLess(transfer,descent);self.assertLess(descent,next_on)

    def test_profiles_are_independent_and_verification_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profiles.json'
            configs={k:defaults(k) for k in BRANDS}
            configs['UR']=replace(configs['UR'],frame=(100,0,0,1,2,3),verified=True)
            save_profiles(configs,path)
            restored=load_profiles(path)
            self.assertEqual(restored['UR'].frame[0],100)
            self.assertEqual(restored['ELITE CS/ES'].frame[0],0)
            self.assertFalse(restored['UR'].verified)

    def test_network_probe_sends_no_command_and_execution_framing(self):
        for brand in BRANDS:
            c=replace(defaults(brand),host='127.0.0.1',verified=True)
            script=render_script(PATHS,0,20,10,c)
            with patch('robot_adapters.socket.create_connection') as connect, patch('robot_control.read_state',return_value={'state':'STOPPED','power':True,'emergency':False,'protective':False}), patch('robot_control.dashboard',return_value='REMOTE') as query:
                client=connect.return_value.__enter__.return_value
                test_connection(c)
                client.sendall.assert_not_called()
                self.assertIn(query.call_args.args[1],('remoteControl -s','is in remote control'))
                send_script(c,script)
                expected=script if brand=='UR' else '\n'.join(line for line in script.splitlines() if line.strip() and not line.lstrip().startswith('#'))+'\n'
                client.sendall.assert_called_once_with(expected.encode('utf-8'))
                self.assertEqual(connect.call_args.args[0],('127.0.0.1',BRANDS[brand]['port']))
            with self.assertRaises(ValueError):send_script(replace(c,verified=False),script)

    def test_invalid_values_and_network_failure_no_retry(self):
        for overrides in ({'name':'x():\nmovej'}, {'orientation':(float('nan'),0,0)}, {'brand':'EC'}, {'port':1.5}, {'output':1.5}):
            with self.assertRaises(ValueError):replace(defaults('UR'),**overrides).validate()
        c=replace(defaults('UR'),host='127.0.0.1',verified=True)
        with patch('robot_adapters.socket.create_connection',side_effect=TimeoutError('timeout')) as connect:
            with self.assertRaises(TimeoutError):send_script(c,render_script(PATHS,0,20,10,c))
            connect.assert_called_once()

if __name__=='__main__':unittest.main()
