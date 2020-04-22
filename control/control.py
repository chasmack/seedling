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
    def __init__(self, name, temp_id, port, onewire, convert_res):
        self.name = name
        self.temp_id = temp_id
        self.port = port
        self.enabled = None
        self.relay = None
        self.setpoint = None
        self.temp_sensor =  DS18B20(onewire, DS18B20_SENSORS[temp_id], convert_res=convert_res)
        self.temp = None

    def status(self):
        return {
            'name': self.name,
            'enabled': self.enabled,
            'relay': self.relay,
            'set': self.setpoint,
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

        # Initialize the control channels

        self.channel = {}
        for name, temp_id, port in CHAN_PARAMS :
            self.channel[name] = ControlChannel(name, temp_id, port, self.onewire, CONVERT_RES)

        # Initialize setpoint and enabled from startup file
        with open(STARTUP_FILE) as f:
            regex = re.compile('(%s):(\d+):(ON|OFF)' % '|'.join(self.channel_names))
            for line in f:
                line = line.strip()
                if line.startswith('#') or line == '':
                    continue
                try:
                    name, sp, en = regex.fullmatch(line).groups()
                    chan = self.channel[name]
                    if chan.port is not None:
                        chan.setpoint = float(sp)
                        chan.enabled = (en == 'ON')
                    else:
                        print('seedling control: Channel "%s" has not control port' % name)
                except AttributeError:
                    print('seedling control: Bad startup command: %s' % line)

        self.msg_queue = msg_queue
        self.rsp_queue = rsp_queue


    @property
    def channels(self):
        ctl_chans = []
        aux_chans = []
        for chan in sorted(self.channel.values(), key=lambda c: c.name):
            if chan.port is None:
                aux_chans.append(chan)
            else:
                ctl_chans.append(chan)
        return ctl_chans + aux_chans

    @property
    def channel_names(self):
        return list(c.name for c in self.channels)

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
                            'chans': list(c.status() for c in self.channels)
                        }
                        self.rsp_queue.put(stat)
                        continue
                    elif cmd == 'END':
                        exit_flag = True
                    elif cmd == 'SET' and len(params) == 2:
                        name, v = params
                        if name in self.channel_names:
                            if self.channel[name].port is not None:
                                if v in ('ON', 'OFF'):
                                    self.channel[name].enabled = (v == 'ON')
                                elif v.isdigit():
                                    self.channel[name].setpoint = float(v)
                                else:
                                    err = 'ERROR: Bad SET parameter: %s' % v
                            else:
                                err = 'ERROR: Channel "%s" has no control port.' % name
                        else:
                            err = 'ERROR: Bad channel name: %s' % c
                    else:
                        err = 'ERROR: Bad command: %s' % msg

                    self.rsp_queue.put(err if err else 'OK')
                    continue

            # print('seedling control: update')

            relays = ~self.gpio.olat()
            for chan in self.channels:
                chan.temp_sensor.convert_t()
                chan.temp = to_fahrenheit(chan.temp_sensor.temperature)

                if chan.port is None:
                    continue

                if chan.enabled:
                    if chan.temp < chan.setpoint - HYSTERESIS:
                        relays |= chan.port
                    elif chan.temp > chan.setpoint + HYSTERESIS:
                        relays &= ~chan.port
                else:
                    relays &= ~chan.port
                chan.relay = relays & chan.port != 0

            relays &= RELAY_MASK
            self.gpio.olat(RELAY_MASK, ~relays)

            t_next += CYCLE_TIME

        print('seedling control: shutdown')
        self.gpio.output_high(RELAY_MASK).config_input(RELAY_MASK)
