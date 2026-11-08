import unittest
from types import SimpleNamespace
from unittest.mock import patch
from robot_window import RobotWindow
from robot_adapters import defaults,render_script


class ExecuteTests(unittest.TestCase):
    def test_explicit_execute_click_sends_without_confirmation(self):
        c=defaults('ELITE CS/ES');c.host='127.0.0.1'
        script=render_script([[(0,0),(1,0)]],0,5,5,c)
        calls=[]
        window=SimpleNamespace(generate=lambda:(c,script),app=SimpleNamespace(start_execution=lambda *args:calls.append(args)))
        with patch('robot_window.messagebox.askyesno',side_effect=AssertionError('Unexpected confirmation')),patch('robot_window.send_script') as send:
            RobotWindow.execute(window)
            self.assertEqual(calls,[(c,script)])
            send.assert_not_called()

    def test_invalid_network_parameters_still_block_send(self):
        c=defaults('UR')
        window=SimpleNamespace(generate=lambda:(c,'unused'),launch=lambda work:work())
        with patch('robot_window.send_script') as send,patch('robot_window.messagebox.showerror') as error:
            RobotWindow.execute(window)
            send.assert_not_called();error.assert_called_once()
