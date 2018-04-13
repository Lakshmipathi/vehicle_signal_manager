# Copyright (C) 2018 Collabora Limited
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Authors:
#  * Guillaume Tucker <guillaume.tucker@collabora.com>

import ipc
import socket
import sys


class StreamIPC(ipc.FilenoIPC):

    def __init__(self, input_stream, output_stream):
        self._in = input_stream
        self._out = output_stream

    def close(self):
        close(self._in)
        close(self._out)

    def fileno(self):
        return self._in.fileno()

    def send(self, signal, value):
        self._write('='.join([signal, value]))

    def receive(self):
        line = self._readline().strip()
        return tuple(s.strip() for s in line.split('='))

    def _write(self, data):
        self._out.write(data)
        self._out.flush()

    def _readline(self):
        return self._in.readline()


class StdioIPC(StreamIPC):

    def __init__(self, *args, **kwargs):
        super(StdioIPC, self).__init__(sys.stdin, sys.stdout, *args, **kwargs)

    def _write(self, data):
        self._out.write(data + '\n')


class SocketIPC(StreamIPC):

    def __init__(self, host, port, *args, **kwargs):
        self._sock = socket.create_connection((host, port))
        self._file = self._sock.makefile('rw')
        super(SocketIPC, self).__init__(self._file, self._file, *args, **kwargs)

    def close(self):
        self._file.close()
        self._sock.close()

    def fileno(self):
        return self._sock.fileno()
