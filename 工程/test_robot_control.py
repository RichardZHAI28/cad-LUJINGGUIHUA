import socket
import struct
import threading
import unittest
from unittest.mock import patch
from dataclasses import replace
from robot_adapters import defaults
from robot_control import parse_state,read_state,dashboard,RobotRunner,connection_report,connection_text


def packet(state='RUNNING',outputs=5):
    mode=bytearray(21);struct.pack_into('>IB',mode,0,21,0)
    mode[15]=1;mode[18]=state=='RUNNING';mode[19]=state=='PAUSED';mode[20]=7
    io=struct.pack('>IBII',13,3,0,outputs)
    data=mode+io
    return struct.pack('>IB',5+len(data),16)+data


class ControlTests(unittest.TestCase):
    def test_connection_report_distinguishes_script_port_from_working_feedback(self):
        c=replace(defaults('ELITE CS/ES'),host='127.0.0.1',port=30002)
        state={'state':'STOPPED','power':True,'emergency':False,'protective':False}
        with patch('robot_control.socket.create_connection',side_effect=TimeoutError('script port blocked')),patch('robot_control.read_state',return_value=state),patch('robot_control.dashboard',return_value='REMOTE') as query:
            report=connection_report(c)
        self.assertFalse(report['connected']);self.assertTrue(report['remote_ready'])
        self.assertFalse(report['interfaces']['脚本']['ok']);self.assertTrue(report['interfaces']['状态']['ok'])
        self.assertIn('30002 失败',connection_text(report));self.assertIn('部分连接',connection_text(report))
        query.assert_called_once_with(c,'remoteControl -s',timeout=1)

    def test_state_feedback_packet_and_corrupt_lengths(self):
        for state in ('RUNNING','PAUSED','STOPPED'):
            result=parse_state(packet(state,32768))
            self.assertEqual(result['state'],state);self.assertEqual(result['outputs'],32768)
            self.assertTrue(result['power']);self.assertFalse(result['emergency'])
        with self.assertRaises(ValueError):parse_state(packet()[:-1])

    def test_primary_socket_handles_fragmented_frames(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1',0));server.listen()
            def worker():
                with server.accept()[0] as client:
                    for b in packet('PAUSED'):client.sendall(bytes([b]))
            thread=threading.Thread(target=worker);thread.start()
            config=replace(defaults('UR'),host='127.0.0.1',state_port=server.getsockname()[1])
            self.assertEqual(read_state(config)['state'],'PAUSED');thread.join(3)

    def test_start_does_not_overwrite_a_running_program(self):
        runner=RobotRunner()
        with patch('robot_control.read_state',return_value={'state':'RUNNING'}),patch('robot_control.send_script') as send:
            with self.assertRaises(ValueError):runner.start(defaults('UR'),'unused')
            send.assert_not_called()

    def test_pause_captures_arc_state_then_turns_it_off(self):
        runner=RobotRunner();runner.config=replace(defaults('ELITE CS/ES'),weld_enabled=True,output=3)
        with patch('robot_control.dashboard') as command,patch.object(runner,'wait_state',return_value={'state':'PAUSED','outputs':8}),patch('robot_control.arc_output') as arc:
            runner.pause();self.assertEqual(runner.state,'PAUSED');self.assertTrue(runner.arc_was_on)
            command.assert_called_once_with(runner.config,'pause');arc.assert_called_once_with(runner.config,False)

    def test_resume_failure_turns_arc_off_and_never_resends_script(self):
        runner=RobotRunner();runner.config=replace(defaults('ELITE CS/ES'),weld_enabled=True);runner.state='PAUSED';runner.arc_was_on=True
        with patch('robot_control.read_state',return_value={'state':'PAUSED'}),patch('robot_control.arc_output') as arc,patch('robot_control.dashboard',side_effect=RuntimeError('Failed to execute: play')),patch('robot_control.send_script') as send:
            with self.assertRaises(RuntimeError):runner.resume()
            self.assertEqual([c.args[1] for c in arc.call_args_list],[True,False]);send.assert_not_called()

    def test_ur_external_pause_never_plays_an_unrelated_loaded_program(self):
        runner=RobotRunner();runner.config=defaults('UR');runner.state='PAUSED'
        with patch('robot_control.dashboard') as command,patch('robot_control.arc_output') as arc:
            with self.assertRaises(ValueError):runner.resume()
            command.assert_not_called();arc.assert_not_called()

    def test_stop_failure_still_attempts_arc_off(self):
        runner=RobotRunner();runner.config=replace(defaults('UR'),weld_enabled=True)
        with patch('robot_control.dashboard',side_effect=TimeoutError('disconnected')),patch('robot_control.arc_output') as arc:
            with self.assertRaises(TimeoutError):runner.stop()
            arc.assert_called_once_with(runner.config,False)

    def test_cancelled_start_never_sends_and_active_config_is_a_snapshot(self):
        runner=RobotRunner();runner.cancel.set()
        with patch('robot_control.send_script') as send:
            with self.assertRaises(RuntimeError):runner.start(defaults('UR'),'unused')
            send.assert_not_called()
        runner.cancel.clear();config=defaults('UR')
        with patch('robot_control.read_state',return_value={'state':'STOPPED','power':True,'emergency':False,'protective':False}),patch('robot_control.dashboard',return_value='true'),patch('robot_control.send_script'),patch.object(runner,'wait_state'):
            runner.start(config,'unused');config.host='changed'
            self.assertNotEqual(runner.config.host,config.host)
