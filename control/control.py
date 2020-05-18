import os
import queue
import time
import re
import itertools

import board
import busio
from control.ds2482 import DS2482
from control.ds18b20 import DS18B20, OneWireDataError, CONVERT_RES_10_BIT
from control.ds18b20 import to_fahrenheit
from control.mcp23008 import MCP23008
from control.mcp23008 import PORT_A0, PORT_A1, PORT_A2, PORT_A3

CYCLE_TIME = 5
HYSTERESIS = 1.0
CONVERT_RES = CONVERT_RES_10_BIT

# Channel name, temperature sensor ID and optional relay port
CHAN_PARAMS = (
    ('A', 'C1', PORT_A0),
    ('B', 'C2', PORT_A1),
    ('C', 'C3', PORT_A2),
    ('D', 'C4', PORT_A3),
    ('C5', 'C5', None),
)

RELAY_MASK = PORT_A0 | PORT_A1 | PORT_A2 | PORT_A3

STARTUP_FILE = os.path.join(os.path.dirname(__file__), 'startup.config')

# Standalone procedure to shutdown the IO
def shutdown():
    i2c = busio.I2C(board.SCL, board.SDA)
    MCP23008(i2c).output_high(RELAY_MASK).config_input(RELAY_MASK)

class ControlChannel:

    # Channels with no control port represent auxiliary temperature channels
    def __init__(self, name, temp_id, onewire, port=None):
        self.name = name
        self.temp_id = temp_id
        self.sensor =  DS18B20(onewire, temp_id, res=CONVERT_RES)
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

        self.msg_queue = msg_queue
        self.rsp_queue = rsp_queue

        self.load_defaults(STARTUP_FILE)

    # Initialize control channels from the startup file
    def load_defaults(self, filename):
        with open(filename) as f:
            regex = re.compile('(%s):(\d+):(ON|OFF)' % '|'.join(self.ctl_names))
            for line in f:
                line = line.strip().upper()
                if line.startswith('#') or line == '':
                    continue
                try:
                    name, sp, en = regex.fullmatch(line).groups()
                    chan = self.ctl_chan[name]
                    chan.set = int(sp)
                    chan.enabled = (en == 'ON')
                except AttributeError:
                    print('seedling control: Bad startup command: %s' % line)

    # Save control channel configuration to the startup file
    def save_defaults(self, filename):
        with open(filename, 'w') as f:
            f.write('# Setpoints at startup\n')
            for chan in self.ctl_chans:
                f.write(('%s:%d:%s' %(chan.name, chan.set, 'ON' if chan.enabled else 'OFF')))

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

            t_wait = t_next - time.monotonic()

            if t_wait > 0:
                # print('seedling control: wait %.3f' % t_wait)

                try:
                    msg = self.msg_queue.get(timeout=t_wait)
                except queue.Empty:
                    # No message, update instrumentation
                    pass
                else:
                    # Process message then back to top of control loop
                    # print('seedling control: msg=%s' % msg)

                    resp = {'error': None}
                    cmd, *params = msg.strip().upper().split()
                    if cmd == 'STAT':
                        resp.update({
                            'ctl_chans': list(chan.stat() for chan in self.ctl_chans),
                            'aux_chans': list(chan.stat() for chan in self.aux_chans)
                        })
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
                                resp.update({'error': 'Bad SET parameter: %s' % val})
                        else:
                            resp.update({'error': 'Bad control channel name: %s' % name})
                    else:
                        resp.update({'error': 'Bad command: %s' % msg})

                    self.rsp_queue.put(resp)
                    continue

            # print('seedling control: update')

            # Update temperatures
            for chan in self.ctl_chans + self.aux_chans:
                try:
                    chan.sensor.convert_t()
                    chan.temp = to_fahrenheit(chan.sensor.temperature)
                except OneWireDataError as e:
                    print('seedling control: DS18b20 measurement error: %s' % e)
                    exit_flag = True
                    break

            if not exit_flag:

                # Get current outputs and invert to use active high logic
                relays = ~self.gpio.olat()
                for chan in self.ctl_chans:
                    if chan.enabled:
                        if chan.temp < chan.set - HYSTERESIS:
                            # Turn the relay port ON
                            relays |= chan.port
                        elif chan.temp > chan.set + HYSTERESIS:
                            # Turn the relay port OFF
                            relays &= ~chan.port
                    else:
                        # Ensure disabled channels are OFF
                        relays &= ~chan.port

                    # Update channel relay status
                    chan.relay = (relays & chan.port) != 0

                self.gpio.olat(RELAY_MASK, ~relays & 0xFF)

            t_next += CYCLE_TIME

        print('seedling control: shutdown')
        self.gpio.output_high(RELAY_MASK).config_input(RELAY_MASK)
