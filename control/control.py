import os
import queue
import time
import re
import itertools

import board
import busio
from control.ds2482 import DS2482
from control.ds18b20 import DS18B20, DS18B20_SENSORS
from control.ds18b20 import CONVERT_RES_9_BIT, CONVERT_RES_10_BIT, CONVERT_RES_11_BIT, CONVERT_RES_12_BIT
from control.ds18b20 import to_fahrenheit
from control.mcp23008 import MCP23008
from control.mcp23008 import PORT_A0, PORT_A1, PORT_A2, PORT_A3

CYCLE_TIME = 5
HYSTERESIS = 1.0
CONVERT_RES = CONVERT_RES_10_BIT

CHAN_PARAMS = (
    ('A', 'C1', PORT_A0),
    ('B', 'C2', PORT_A1),
    ('C', 'C3', PORT_A2),
    ('D', 'C4', PORT_A3),
    ('C5', 'C5', None),
)

RELAY_MASK = PORT_A0 | PORT_A1 | PORT_A2 | PORT_A3

STARTUP_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'startup.config'))

# Standalone procedure to shutdown the IO
def shutdown():
    i2c = busio.I2C(board.SCL, board.SDA)
    MCP23008(i2c).output_high(RELAY_MASK).config_input(RELAY_MASK)

class ControlChannel:

    # Channels with no control port represent auxiliary temperature channels
    def __init__(self, name, temp_id, onewire, port=None):
        self.name = name
        self.temp_id = temp_id
        self.sensor =  DS18B20(onewire, DS18B20_SENSORS[temp_id], convert_res=CONVERT_RES)
        self.port = port
        self.temp = None
        self.enabled = False
        self.set = None
        self.relay = None

    def stat(self):
        return {
            'name': self.name,
            'temp': self.temp,
            'enabled': self.enabled,
            'set': self.set,
            'relay': self.relay
        } if self.port is not None else {
            'name': self.name,
            'temp': self.temp
        }

class Control:

    def __init__(self, msg_queue, rsp_queue):

        self.i2c = busio.I2C(board.SCL, board.SDA)

        # Initialize the GPIO, relays off (ports are active low), configure as outputs
        self.gpio = MCP23008(self.i2c)
        self.gpio.output_high(RELAY_MASK).config_output(RELAY_MASK)

        # Initialize the 1-wire bus and temperature sensors
        self.onewire = DS2482(self.i2c, active_pullup=True)

        # Initialize the control and auxiliary temperature channels
        self.ctl_chan = {}
        self.aux_chan = {}
        for name, temp_id, port in CHAN_PARAMS :
            if port is None:
                self.aux_chan[name] = ControlChannel(name, temp_id, self.onewire)
            else:
                self.ctl_chan[name] = ControlChannel(name, temp_id, self.onewire, port)

        # Initialize control channels from the startup file
        with open(STARTUP_FILE) as f:
            regex = re.compile('(%s):(\d+):(ON|OFF)' % '|'.join(self.ctl_names))
            for line in f:
                line = line.strip()
                if line.startswith('#') or line == '':
                    continue
                try:
                    name, sp, en = regex.fullmatch(line).groups()
                    chan = self.ctl_chan[name]
                    chan.set = int(sp)
                    chan.enabled = (en == 'ON')
                except AttributeError:
                    print('seedling control: Bad startup command: %s' % line)

        self.msg_queue = msg_queue
        self.rsp_queue = rsp_queue

    # Sorted lists of channels and channel names

    @property
    def ctl_chans(self):
         return sorted(self.ctl_chan.values(), key=lambda c: c.name)

    @property
    def ctl_names(self):
        return sorted(self.ctl_chan.keys())

    @property
    def aux_chans(self):
         return sorted(self.aux_chan.values(), key=lambda c: c.name)

    @property
    def aux_names(self):
        return sorted(self.aux_chan.keys())

    def main_loop(self):

        # Time at next instrumentation update
        t = time.monotonic()
        t_next = t - t % CYCLE_TIME

        exit_flag = False
        while not exit_flag:

            # print('seedling control: loop')

            t = time.monotonic()
            t_wait = t_next - time.monotonic()

            if t_wait > 0:
                # print('seedling control: wait %.3f' % t_wait)

                try:
                    msg = self.msg_queue.get(timeout=t_wait)
                except queue.Empty:
                    # No message, update instrumentation
                    pass
                else:
                    # print('seedling control: msg=%s' % msg)

                    err = None
                    cmd, *params = msg.upper().split()
                    if cmd == 'STAT':
                        stat = {
                            'ctl_chans': list(chan.stat() for chan in self.ctl_chans),
                            'aux_chans': list(chan.stat() for chan in self.aux_chans)
                        }
                        self.rsp_queue.put(stat)
                        continue
                    elif cmd == 'END':
                        exit_flag = True
                    elif cmd == 'SET' and len(params) == 2:
                        name, val = params
                        if name in self.ctl_names:
                            if val in ('ON', 'OFF'):
                                self.ctl_chan[name].enabled = (val == 'ON')

                            elif val.startswith('+') and val[1:].isdigit():
                                self.ctl_chan[name].set += int(val[1:])

                            elif val.startswith('-') and val[1:].isdigit():
                                self.ctl_chan[name].set -= int(val[1:])

                            elif val.isdigit():
                                self.ctl_chan[name].set = int(val)

                            else:
                                err = 'ERROR: Bad SET parameter: %s' % val

                        else:
                            err = 'ERROR: Bad channel name: %s' % c
                    else:
                        err = 'ERROR: Bad command: %s' % msg

                    self.rsp_queue.put(err if err else 'OK')
                    continue

            # print('seedling control: update')

            for chan in self.aux_chans:
                chan.sensor.convert_t()
                chan.temp = to_fahrenheit(chan.sensor.temperature)

            relays = ~self.gpio.olat()
            for chan in self.ctl_chans:
                chan.sensor.convert_t()
                chan.temp = to_fahrenheit(chan.sensor.temperature)
                if chan.enabled:
                    if chan.temp < chan.set - HYSTERESIS:
                        relays |= chan.port
                    elif chan.temp > chan.set + HYSTERESIS:
                        relays &= ~chan.port
                else:
                    relays &= ~chan.port
                chan.relay = relays & chan.port != 0

            relays &= RELAY_MASK
            self.gpio.olat(RELAY_MASK, ~relays)

            t_next += CYCLE_TIME

        print('seedling control: shutdown')
        self.gpio.output_high(RELAY_MASK).config_input(RELAY_MASK)
