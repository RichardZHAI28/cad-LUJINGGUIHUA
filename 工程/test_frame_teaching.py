import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.vendor'))
import math
import struct
import socket
import threading
import unittest
from unittest.mock import patch
import numpy as np
from scipy.spatial.transform import Rotation
from frame_teaching import teach_frame,frame_rotation,project_axis
from robot_control import parse_state,read_teaching_sample
from robot_adapters import defaults,render_script
from test_robot_control import packet


class TeachingTests(unittest.TestCase):
    def test_axis_camera_is_orthonormal_and_right_handed(self):
        matrix=np.array([project_axis(v) for v in np.eye(3)]).T
        right,up=matrix[0],-matrix[1]
        np.testing.assert_allclose(np.cross(right,up),np.ones(3)/math.sqrt(3))
        np.testing.assert_allclose(matrix@matrix.T,np.eye(2),atol=1e-12)
        frame,axes=teach_frame([(0,0,0),(100,0,0),(20,100,0)],'ELITE CS/ES')
        np.testing.assert_allclose(np.cross(axes['x'],axes['y']),axes['z'])
        self.assertEqual(project_axis(axes['z'])[0],0)
        self.assertLess(project_axis(axes['z'])[1],0)

    def test_arbitrary_tilted_frame_and_both_brand_encodings(self):
        rotation=Rotation.from_euler('xyz',[.4,-.6,1.2]).as_matrix()
        origin=np.array([400,-200,300])
        points=[origin,origin+rotation[:,0]*100,origin+rotation[:,0]*30+rotation[:,1]*80]
        for brand in ('UR','ELITE CS/ES'):
            frame,axes=teach_frame(points,brand)
            np.testing.assert_allclose(frame[:3],origin)
            np.testing.assert_allclose(frame_rotation(frame,brand).as_matrix(),rotation,atol=1e-12)
            np.testing.assert_allclose(axes['z'],rotation[:,2],atol=1e-12)
            c=defaults(brand);c.frame=frame
            self.assertIn('user_frame = ',render_script([[(0,0),(10,0)]],0,20,10,c))

    def test_reversed_y_side_reverses_z_and_degenerate_points_are_blocked(self):
        _,axes=teach_frame([(0,0,0),(100,0,0),(0,-100,0)],'ELITE CS/ES')
        np.testing.assert_allclose(axes['z'],[0,0,-1])
        for points in ([(0,0,0),(0,0,0),(0,10,0)],[(0,0,0),(100,0,0),(50,0,0)],
                       [(0,0,0),(100,0,0),(50,.1,0)],[(0,0,0),(100,0,0),(0,float('nan'),0)]):
            with self.assertRaises(ValueError):teach_frame(points,'UR')

    def test_cartesian_packet_decode_and_mm_conversion_without_sending(self):
        raw=packet('STOPPED')
        cart=struct.pack('>IB12d',101,4,.4,-.2,.3,0,0,1.2,0,0,.1,0,0,0)
        raw=struct.pack('>I',len(raw)+len(cart))+raw[4:]+cart
        state=parse_state(raw)
        for brand in ('UR','ELITE CS/ES'):
            c=defaults(brand)
            with patch('robot_control.read_state',return_value=state),patch('robot_control.time.sleep'),patch('robot_control.send_script') as send:
                point,tcp=read_teaching_sample(c)
                self.assertEqual(point,(400,-200,300));self.assertEqual(tcp[2],100)
                send.assert_not_called()
        with self.assertRaises(ValueError):parse_state(raw[:-1])

    def test_capture_rejects_motion_and_tcp_mismatch(self):
        c=defaults('ELITE CS/ES')
        state={'state':'STOPPED','emergency':False,'protective':False,'tcp_pose':(.4,.2,.3,0,0,0),'tcp_offset':(0,0,.1,0,0,0)}
        with patch('robot_control.time.sleep'):
            with patch('robot_control.read_state',side_effect=[state,{**state,'tcp_pose':(.5,.2,.3,0,0,0)}]):
                with self.assertRaisesRegex(ValueError,'移动'):read_teaching_sample(c)
            c.tcp_mode='configured'
            with patch('robot_control.read_state',return_value=state):
                with self.assertRaisesRegex(ValueError,'不一致'):read_teaching_sample(c)

    def test_two_fragmented_socket_samples_are_read_only_for_both_brands(self):
        for brand in ('UR','ELITE CS/ES'):
            with self.subTest(brand=brand),socket.socket() as server:
                server.bind(('127.0.0.1',0));server.listen();server.settimeout(5)
                raw=packet('STOPPED')
                cart=struct.pack('>IB12d',101,4,.4,-.2,.3,0,0,0,0,0,.1,0,0,0)
                raw=struct.pack('>I',len(raw)+len(cart))+raw[4:]+cart
                received=[];errors=[]
                def worker():
                    try:
                        for _ in range(2):
                            with server.accept()[0] as client:
                                client.settimeout(3)
                                for i in range(0,len(raw),7):client.sendall(raw[i:i+7])
                                received.append(client.recv(1))
                    except Exception as exc:errors.append(str(exc))
                thread=threading.Thread(target=worker,daemon=True);thread.start()
                c=defaults(brand);c.host='127.0.0.1';c.state_port=server.getsockname()[1]
                self.assertEqual(read_teaching_sample(c)[0],(400,-200,300))
                thread.join(5);self.assertFalse(errors);self.assertEqual(received,[b'',b''])


if __name__=='__main__':unittest.main()
