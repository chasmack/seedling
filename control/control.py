import os
import queue
import time

import board
import busio
from control.ds2482 import DS2482
from control.ds18b20 import DS18B20, DS18B20_SENSORS
from control.ds18b20 import CONVERT_RES_9_BIT, CONVERT_RES_10_BIT, CONVERT_RES_11_BIT, CONVERT_RES_12_BIT
from control.ds18b20 import to_fahrenheit
from control.mcp23008 import MCP23008
from control.mcp23008 import PORT_A0, PORT_A1, PORT_A2, PORT_A3

NCHANNELS = 4
CYCLE_TIME = 10
HYSTERESIS = 1.0
CONVERT_RES = CONVERT_RES_9_BIT

TEMP_IDS = (('C1', 'C3'), ('C2', 'C4'), ('C5',), ())

RELAY_PORTS = (PORT_A0, PORT_A1, PORT_A2, PORT_A3)
RELAY_MASK = PORT_A0 | PORT_A1 | PORT_A2 | PORT_A3

STARTUP_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'startup.config'))

# Standalone procedure to shutdown the IO
def shutdown():
    i2c = busio.I2C(board.SCL, board.SDA)
    MCP23008(i2c).output_high(RELAY_MASK).config_input(RELAY_MASK)

class ControlChannel:
    def __init__(self, relay_port=None, temp_ids=None):
        self.relay_port = relay_port
        self.relay = None
        self.setpoint = None
        self.temp_ids = temp_ids
        self.temp_sensors = []
        self.temps = []

    def status(self):
        return [self.relay, self.setpoint, *self.temps]

class Control:

    def __init__(self, mqueue, rqueue):

        self.i2c = busio.I2C(board.SCL, board.SDA)

        # Initialize the GPIO, relays off (ports are active low), configure as outputs
        self.gpio = MCP23008(self.i2c)
        self.gpio.output_high(RELAY_MASK).config_output(RELAY_MASK)

        # Initialize the 1-wire bus and temperature sensors
        self.onewire = DS2482(self.i2c, active_pullup=True)

        # Get startup setpoints
        setpoints = []
        with open(STARTUP_FILE) as f:
            for line in f:
                if line.startswith('#') or line.strip() == '':
                    continue
                setpoints = line.strip().split(',')
                break
        setpoints = list(float(sp) for sp in setpoints)

        # Initialize the channel objects
        self.channels = []
        for i in range(NCHANNELS):
            c = ControlChannel(RELAY_PORTS[i], TEMP_IDS[i])
            for id in c.temp_ids:
                c.temp_sensors.append(DS18B20(self.onewire, DS18B20_SENSORS[id], convert_res=CONVERT_RES))
            if len(setpoints) > i:
                c.setpoint = setpoints[i]
            self.channels.append(c)

        self.mequeue = mqueue
        self.rqueue = rqueue

    def main_loop(self):

        exit_flag = False
        while not exit_flag:

            # print('control loop')

            relays = ~self.gpio.olat()
            for chan in self.channels:
                chan.temps = []
                for sens in chan.temp_sensors:
                    sens.convert_t()
                    chan.temps.append(to_fahrenheit(sens.temperature))

                if chan.setpoint and len(chan.temps):
                    t = chan.temps[0]
                    if t < chan.setpoint - HYSTERESIS:
                        relays |= chan.relay_port
                    elif t > chan.setpoint + HYSTERESIS:
                        relays &= ~chan.relay_port
                else:
                    relays &= ~chan.relay_port
                chan.relay = relays & chan.relay_port != 0

            relays &= RELAY_MASK
            self.gpio.olat(RELAY_MASK, ~relays)

            # Time to next cycle
            t = time.monotonic()
            t = CYCLE_TIME - t % CYCLE_TIME

            # print('control wait %.3f' % t)
            try:
                msg = self.mequeue.get(timeout=t).lower()
            except queue.Empty:
                pass
            else:
                print('control msg: %s' % msg)

                if msg == 'end':
                    exit_flag = True
                else:
                    err = None
                    msg = msg.split()
                    if len(msg) == 3 and msg[0] == 'set':
                        try:
                            n = int(msg[1])
                            if not 0 < n < NCHANNELS + 1:
                                raise ValueError('Channel number must be from 1 to %d' % NCHANNELS)
                            sp = float(msg[2])
                            self.channels[n - 1].setpoint = sp
                        except ValueError as e:
                            err = 'Bad command: %s' % e
                    elif len(msg) == 1 and msg[0] == 'stat':
                        pass
                    else:
                        err = 'Bad command: %s' % ' '.join(msg)

                    if err:
                        self.rqueue.put('ERROR: %s' % err)
                    else:
                        self.rqueue.put(list(chan.status() for chan in self.channels))

        print('control shutdown')
        self.gpio.output_high(RELAY_MASK).config_input(RELAY_MASK)

