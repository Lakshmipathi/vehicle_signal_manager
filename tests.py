#!/usr/bin/env python3
# Copyright (C) 2017 Collabora
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# Authors: Shane Fagan - shane.fagan@collabora.com

import os
import time
import unittest
from subprocess import Popen, PIPE


RULES_PATH = os.path.abspath(os.path.join('.', 'sample_rules'))
LOGS_PATH = os.path.abspath(os.path.join('.', 'sample_logs'))
SIGNAL_FORMAT = '{},[SIGNUM],\'{}\'\n'
VSM_LOG_FILE = 'vsm-tests.log'

def format_ipc_input(data):
    return [ (x.strip(), y.strip()) for x, y in \
             [ elm.split('=') for elm in data.split('\n') ] ]

def _remove_timestamp(output_string):
    # strip any prepended timestamp, if it exists
    output = ''
    for line in output_string.splitlines():
        try:
            timestamp, remainder = line.split(',', 1)
            output += remainder
        except ValueError:
            output += line

        # this re-adds a trailing newline
        output += '\n'

    return output


class TestVSM(unittest.TestCase):
    ipc_module = None

    def setUp(self):
        if TestVSM.ipc_module == 'zeromq':
            self._init_zeromq()

    def tearDown(self):
        if TestVSM.ipc_module == 'zeromq':
            self._tear_down_zeromq()

    def _init_zeromq(self):
        import zmq
        from ipc.zeromq import SOCKET_ADDR
        self._zmq_addr = SOCKET_ADDR
        context = zmq.Context()
        self._zmq_socket = context.socket(zmq.PAIR)
        self._zmq_socket.connect(self._zmq_addr)

    def _tear_down_zeromq(self):
        self._zmq_socket.close()

    def _send(self, signal, value):
        if TestVSM.ipc_module == 'zeromq':
            self._zmq_socket.send_pyobj((signal, value))
            return

        raise NotImplemented

    def _receive(self):
        if TestVSM.ipc_module == 'zeromq':
            return self._zmq_socket.recv_pyobj()

        raise NotImplemented


    def run_vsm(self, name, input_data, expected_output,
                use_initial=True, send_quit=False, replay_case=None,
                wait_time_ms=0):
        conf = os.path.join(RULES_PATH, name + '.yaml')
        initial_state = os.path.join(RULES_PATH, name + '.initial.yaml')

        cmd = ['./vsm' ]

        # Direct verbose output (including state dumps) to log file so the tests
        # can parse them.
        cmd += [ '--log-file={}'.format(VSM_LOG_FILE) ]

        if use_initial and os.path.exists(initial_state):
            cmd += ['--initial-state={}'.format(initial_state)]

        cmd += [conf]

        if replay_case:
            replay_file = os.path.join(LOGS_PATH, replay_case + '.log')

            if os.path.exists(replay_file):
                cmd += ['--replay-log-file={}'.format(replay_file)]

        if TestVSM.ipc_module:
            cmd += [ '--ipc-module={}'.format(TestVSM.ipc_module) ]

        if TestVSM.ipc_module == 'zeromq':
            process = Popen(cmd)

            process_output = ''
            for signal, value in format_ipc_input(input_data):
                self._send(signal, value)
                # Record sent signal directly from the test.
                process_output += SIGNAL_FORMAT.format(signal, value)

            # Send 'quit' for those tests with no signal reply, otherwise
            # they will be stuck on 'receive'.
            if send_quit:
                self._send('quit', '')

            sig, val = self._receive()
            # Give some time for the logger to write all the output.
            time.sleep(0.01)
            process.terminate()

            process_output += '' if (sig == '') else SIGNAL_FORMAT.format(sig, val)
        else:
            process = Popen(cmd, stdin=PIPE, stdout=PIPE)

            timeout_s = 2
            if wait_time_ms > 0:
                timeout_s = wait_time_ms / 1000

            output, _ = process.communicate(input=input_data.encode(),
                    timeout=timeout_s)
            cmd_output = output.decode()

            process_output = _remove_timestamp(cmd_output)

        # Read state dump from log file.
        with open(VSM_LOG_FILE) as f:
            state_output = f.read()

        log_output = _remove_timestamp(state_output)
        output_final = log_output + process_output

        self.assertEqual(output_final , expected_output)


    def test_simple0(self):
        input_data = 'transmission_gear = "reverse"'
        expected_output = '''
transmission_gear,[SIGNUM],'reverse'
State = {
transmission_gear = reverse
}
car.backup,[SIGNUM],'True'
condition: (transmission_gear == 'reverse') => True
transmission_gear,[SIGNUM],'"reverse"'
car.backup,[SIGNUM],'True'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n')

    def test_simple0_delayed(self):
        input_data = 'transmission_gear = "reverse"'
        expected_output = '''
transmission_gear,[SIGNUM],'reverse'
State = {
transmission_gear = reverse
}
condition: (transmission_gear == 'reverse') => True
car.backup,[SIGNUM],'True'
transmission_gear,[SIGNUM],'"reverse"'
car.backup,[SIGNUM],'True'
        '''
        self.run_vsm('simple0_delay', input_data, expected_output.strip() + '\n')

    def test_simple0_uninteresting(self):
        input_data = 'phone_call = "inactive"'
        expected_output = '''
phone_call,[SIGNUM],'inactive'
State = {
phone_call = inactive
}
condition: (phone_call == 'active') => False
phone_call,[SIGNUM],'"inactive"'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_initial(self):
        input_data = 'damage = true'
        expected_output = '''
damage,[SIGNUM],True
State = {
damage = True
moving = false
}
car.stop,[SIGNUM],'True'
condition: (moving != True and damage == True) => True
damage,[SIGNUM],'true'
car.stop,[SIGNUM],'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n')

    def test_simple2_initial_uninteresting(self):
        input_data = 'moving = false'
        expected_output = '''
moving,[SIGNUM],False
State = {
moving = False
}
moving,[SIGNUM],'false'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_modify_uninteresting(self):
        input_data = 'moving = true\ndamage = true'
        expected_output = '''
moving,[SIGNUM],True
State = {
moving = True
}
condition: (moving != True and damage == True) => False
damage,[SIGNUM],True
State = {
damage = True
moving = True
}
condition: (moving != True and damage == True) => False
moving,[SIGNUM],'true'
damage,[SIGNUM],'true'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_multiple_signals(self):
        input_data = 'moving = false\ndamage = true'
        expected_output = '''
moving,[SIGNUM],False
State = {
moving = False
}
damage,[SIGNUM],True
State = {
damage = True
moving = False
}
car.stop,[SIGNUM],'True'
condition: (moving != True and damage == True) => True
moving,[SIGNUM],'false'
damage,[SIGNUM],'true'
car.stop,[SIGNUM],'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n', False)

    def test_simple0_log_replay(self):
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = ''
        expected_output = '''
phone_call,[SIGNUM],'active'
State = {
phone_call = active
}
car.stop,[SIGNUM],'True'
car.stop,[SIGNUM],'True'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n',
                replay_case='simple0-replay', wait_time_ms=5000)

    @unittest.skip("delays not yet implemented")
    def test_delay(self):
        input_data = ''
        expected_output = '''
lights.external.headlights,[SIGNUM],'True'
        '''
        # NOTE: ideally, this would ensure the delay in output
        self.run_vsm('delay', input_data, expected_output.strip() + '\n', False)

    @unittest.skip("exclusive conditions not yet implemented")
    def test_exclusive_conditions(self):
        input_data = 'remote_key.command = "unlock"\nlock_state = true\nremote_key.command = "lock"'
        expected_output = '''
lock_state,[SIGNUM],'False'
horn,[SIGNUM],'True'
        '''
        self.run_vsm('exclusive_conditions', input_data, expected_output.strip() + '\n', False)

    @unittest.skip("subclauses, arithmetic, booleans not yet implemented")
    def test_subclauses_arithmetic_booleans(self):
        input_data = 'flux_capacitor.energy_generated = 1.1\nmovement.speed = 140'
        expected_output = '''
lights.external.time_travel_imminent
lights.internal.time_travel_imminent
        '''
        self.run_vsm('subclauses_arithmetic_booleans', input_data,
                expected_output.strip() + '\n', False)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVSM)
    unittest.TextTestRunner(verbosity=2).run(suite)

    TestVSM.ipc_module = 'zeromq'
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVSM)
    unittest.TextTestRunner(verbosity=2).run(suite)
