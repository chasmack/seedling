import os, stat, pwd, grp, math
import time, threading, platform
import posix_ipc
import sqlite3
import logging
from datetime import datetime, timedelta

from seedling import DATABASE, MQUEUE_CMD

from control.ds18b20 import DS18B20, OneWireDataError
from control.mcp23008 import MCP23008
from control.mcp23008 import PORT_A0, PORT_A1, PORT_A2, PORT_A3
from control.bmp280 import BMP280, BMP280_MODE_FORCED, BMP280_FILTER_COEFF_4
from control.bmp280 import BMP280_OS_MODE_HIGH_RESOLUTION

from control.daemon import daemon

HOSTNAME = platform.uname().node

# Run controller as a daemon process
DAEMON_PROCESS = True

# The user/group of the wsgi app to permit access to the message queue
WSGI_USER = 'www-data'
WSGI_GROUP = 'www-data'

# PID file for finding the daemon
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PID_FILE = os.path.join(ROOT_DIR, 'controller.pid')

# Log file and level
LOG_FILE = os.path.join(ROOT_DIR, 'log/controller.log')
LOG_FORMAT = '%(asctime)s %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%x %X'
LOG_LEVEL = logging.WARNING

# A list of relays with their port
RELAY = {
    'A': PORT_A0,
    'B': PORT_A1,
    'C': PORT_A2,
    'D': PORT_A3
}
RELAY_MASK = PORT_A0 | PORT_A1 | PORT_A2 | PORT_A3

# A list of temperature sensors
# TEMP_SENSORS = ['D1', 'D2']
TEMP_SENSORS = ['C1', 'C2', 'C3', 'C4', 'C5']

# Retry temperature readings on error
TEMP_SENSOR_RETRIES = 2

RELAY_PERIOD = 10 * 60
TEMP_PERIOD = 5 * 60
ENVIRON_PERIOD = 5 * 60
LOOP_PERIOD = 5
MAINT_PERIOD = 8 * 3600

# Keep the previous AVERAGE_SAMPLES temperatures for calculation of delta
AVERAGE_SAMPLES = 3


class Control(daemon):

    def __init__(self):

        self.daemon_process = DAEMON_PROCESS

        # Set up logging
        logging.basicConfig(
            filename=LOG_FILE if self.daemon_process else None,
            level=LOG_LEVEL,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT
        )

        super(Control, self).__init__(PID_FILE)

    def stop(self):

        # New instance sends a STOP command and exits.
        mq = posix_ipc.MessageQueue(MQUEUE_CMD)
        success = None
        try:
            # this fails after timeout if the queue is full
            logging.info('Sending STOP message.')
            mq.send('STOP', timeout=5)

            # wait for the controller to pick up the message
            for i in range(10):
                if mq.current_messages == 0:
                    success = True
                    break
                time.sleep(0.500)

        except posix_ipc.BusyError:
            success = False

        if success:
            logging.info('Done.')
            exit(0)
        else:
            logging.error('Controller not responding.')
            exit(1)

    def relay_updater(self):

        # Startup the device
        self.smbus_lock.acquire()
        gpio_device = MCP23008()
        gpio_device.output_high(RELAY_MASK)
        gpio_device.config_output(RELAY_MASK)
        self.smbus_lock.release()

        # A database connection and cursor
        con = sqlite3.connect(DATABASE)
        cur = con.cursor()

        last_maint = datetime.now()

        while self.run:

            # seconds into the cycle
            tc = time.time() % RELAY_PERIOD

            # next event time is smallest event time including end of cycle turn-off greater than tc
            dutys = set([1.0 - self.relay[r]['duty'] for r in self.relay.keys()] + [1.0])
            for d in sorted(dutys):
                te = d * RELAY_PERIOD
                if te > tc:
                    break

            # seconds tc is ahead of loop cycle
            ts = tc % LOOP_PERIOD

            # number of whole loop cycles from start of loop to end of loop with event
            count = math.ceil((te - (tc - ts)) / LOOP_PERIOD)

            # logging.info('relay_updater: tc=%.2f te=%.2f ts=%.2f count=%d', tc, te, ts, count)

            while self.run:

                if count > 0 and not self.update_relays:

                    # sync to loop cycle in first loop
                    time.sleep(LOOP_PERIOD - ts)
                    count -= 1
                    ts = 0

                else:

                    # Update relays
                    self.smbus_lock.acquire()
                    self.update_relays = False
                    dt =  datetime.now().replace(microsecond=0)

                    t = time.time()
                    tc = t % RELAY_PERIOD
                    relay_status = ~gpio_device.olat(RELAY_MASK) & RELAY_MASK
                    for r in sorted(self.relay.keys()):

                        # All relays start the cycle in the OFF state except for duty equals 1.0
                        # which is always ON. At t equals tc + RELAY_PERIOD * (1.0 - duty) the relay
                        # changes state to ON and remains ON until the end of the cycle. This setup
                        # allows for staggered turn-on times to reduce transient power surges.

                        td = (1.0 - self.relay[r]['duty']) * RELAY_PERIOD

                        if (relay_status & self.relay[r]['port']) != 0 and tc < td:
                                # Relay is ON prior to td, turn it OFF
                                gpio_device.output_high(self.relay[r]['port'])

                        elif (relay_status & self.relay[r]['port']) == 0 and tc > td:
                            # Relay is OFF after td, turn it ON
                            gpio_device.output_low(self.relay[r]['port'])

                    relay_status = ~gpio_device.olat(RELAY_MASK) & RELAY_MASK
                    self.smbus_lock.release()

                    # Print updated status
                    relay_str = 'Relays:'
                    for r in sorted(self.relay.keys()):
                        state = 1 if (relay_status & self.relay[r]['port']) else 0
                        duty = self.relay[r]['duty']
                        relay_str += '  %s:%s (%.2f)' % (r, 'ON ' if state else 'OFF', duty)
                        cur.execute('INSERT INTO relay VALUES(?,?,?,?);', [dt, r, duty, state])

                    logging.info(relay_str)
                    con.commit()

                    # Run through the main updater loop
                    break

            if (datetime.now() - last_maint).total_seconds() > MAINT_PERIOD:

                logging.info('Relays: Database maintenance.')

                # delete older database records
                cur.execute("""
                    DELETE FROM relay WHERE dt < datetime('now', 'localtime', '-12 hours');
                """)
                con.commit()
                last_maint = datetime.now()

        # Shutdown
        self.smbus_lock.acquire()
        gpio_device.output_high(RELAY_MASK)  # relays off (high)
        gpio_device.config_input(RELAY_MASK)  # all inputs
        self.smbus_lock.release()
        con.close()

    def temp_updater(self):

        # The temperature updater reads the temperature sensors every TEMP_PERIOD seconds
        # and writes the results to the database. The thread wakes every LOOP_PERIOD seconds
        # to check if the controller is requesting the thread to terminate.

        # Startup the temperature sensor
        self.smbus_lock.acquire()
        temp_device = DS18B20()
        self.smbus_lock.release()

        temps = {}
        for s in TEMP_SENSORS:
            temps[s] = []

        # A database connection and cursor
        con = sqlite3.connect(DATABASE)
        cur = con.cursor()

        last_maint = datetime.now()

        while self.run:

            # seconds into the update cycle
            tc = time.time() % TEMP_PERIOD

            # next update event relative start of update cycle
            te = TEMP_PERIOD

            # seconds tc is ahead of loop cycle
            ts = tc % LOOP_PERIOD

            # number of loop cycles from current loop to end of loop with event
            count = math.ceil((te - (tc - ts)) / LOOP_PERIOD)

            logging.debug('temp_updater: tc=%.2f te=%.2f ts=%.2f count=%d', tc, te, ts, count)

            while self.run:

                if count > 0:

                    # sync to loop cycle in first loop
                    time.sleep(LOOP_PERIOD - ts)
                    count -= 1
                    ts = 0

                else:

                    # Update temperatures
                    dt = datetime.now().replace(microsecond=0)

                    temp_str = 'Temp:'
                    for s in sorted(TEMP_SENSORS):

                        temp = None
                        retries = TEMP_SENSOR_RETRIES
                        while temp is None and retries > 0:
                            try:
                                self.smbus_lock.acquire()
                                temp = temp_device.temperature(s)
                            except OneWireDataError:
                                retries -= 1
                            finally:
                                self.smbus_lock.release()

                        if temp is None:
                            logging.info('ERROR reading sensor %s', s)

                        temps[s].append(temp)
                        a = sum(temps[s][:-1]) / len(temps[s][:-1]) if temps[s][:-1] else temps[s][-1]

                        # Delta compares current sample to mean of previous AVERAGE_SAMPLES
                        # values and is adjusted to represent the change per sample period.
                        d = (temps[s][-1] - a) / ((AVERAGE_SAMPLES + 1) / 2)

                        temp_str += '  %s:%.1f (%+.1f)' % (s, temps[s][-1], d)
                        if len(temps[s]) > AVERAGE_SAMPLES:
                            temps[s].pop(0)

                        cur.execute('INSERT INTO temperature VALUES (?,?,?)', [dt, s, temps[s][-1]])

                    con.commit()
                    logging.info(temp_str)

                    # Run through the main updater loop
                    break

            if (datetime.now() - last_maint).total_seconds() > MAINT_PERIOD:

                logging.info('Temp: Database maintenance.')

                # delete older database records
                cur.execute("""
                    DELETE FROM temperature WHERE dt < datetime('now', 'localtime', '-12 hours');
                """)
                con.commit()
                last_maint = datetime.now()

        # Shutdown
        self.smbus_lock.acquire()
        temp_device.master_reset()
        self.smbus_lock.release()
        con.close()

    def env_updater(self):

        # The environment updater reads the pressure and temperature from the BMP280 every
        # ENVIRON_PERIOD seconds and writes the results to the database. The thread wakes
        # every LOOP_PERIOD seconds to check if the controller is requesting the thread to terminate.

        # Startup the sensor
        self.smbus_lock.acquire()
        try:
            bmp_device = BMP280()
            bmp_device.os_mode(BMP280_OS_MODE_HIGH_RESOLUTION)
            bmp_device.config(BMP280_FILTER_COEFF_4)
        except:
            logging.error('Unable to initialize BMP280.')
            return
        finally:
            self.smbus_lock.release()

        # A database connection and cursor
        con = sqlite3.connect(DATABASE)
        cur = con.cursor()

        last_maint = datetime.now()

        while self.run:

            # seconds into the update cycle
            tc = time.time() % ENVIRON_PERIOD

            # next update event relative start of update cycle
            te = ENVIRON_PERIOD

            # seconds tc is ahead of loop cycle
            ts = tc % LOOP_PERIOD

            # number of loop cycles from current loop to end of loop with event
            count = math.ceil((te - (tc - ts)) / LOOP_PERIOD)

            # logging.info('env_updater: tc=%.2f te=%.2f ts=%.2f count=%d', tc, te, ts, count)

            while self.run:

                if count > 0:

                    # sync to loop cycle in first loop
                    time.sleep(LOOP_PERIOD - ts)
                    count -= 1
                    ts = 0

                else:

                    # Update pressure and temperature
                    self.smbus_lock.acquire()
                    dt = datetime.now().replace(microsecond=0)

                    bmp_device.convert(BMP280_MODE_FORCED)
                    pres, temp = bmp_device.read_sensor()
                    self.smbus_lock.release()

                    pres /= 100  # Pressure in hPa
                    temp = temp * 9 / 5 + 32  # temperature in degrees fahrenheit
                    logging.info('Pressure: %.2f hPa  Temperature: %.2f', pres, temp)

                    cur.execute('INSERT INTO environment VALUES (?,?,?)', [dt, pres, temp])
                    con.commit()

                    # Run through the main updater loop
                    break

            if (datetime.now() - last_maint).total_seconds() > MAINT_PERIOD:

                logging.info('Env: Database maintenance.')

                # delete older database records
                cur.execute("""
                    DELETE FROM environment WHERE dt < datetime('now', 'localtime', '-12 hours');
                """)
                con.commit()
                last_maint = datetime.now()

        # Shutdown
        self.smbus_lock.acquire()
        bmp_device.reset()
        self.smbus_lock.release()
        con.close()

    def run(self):

        # Delete any existing message queue
        try:
            self.mqueue = posix_ipc.MessageQueue(MQUEUE_CMD, flags=0)
            self.mqueue.close()
            self.mqueue.unlink()
        except posix_ipc.ExistentialError:
            pass

        # Create the message queue and make sure the wsgi app can access it
        self.mqueue = posix_ipc.MessageQueue(MQUEUE_CMD, flags=posix_ipc.O_CREAT, max_messages=1)
        os.fchmod(self.mqueue.mqd, stat.S_IRUSR | stat.S_IWUSR)
        os.fchown(self.mqueue.mqd, pwd.getpwnam(WSGI_USER).pw_uid, grp.getgrnam(WSGI_GROUP).gr_gid)

        # A lock for the message handler
        self.mqueue_lock = threading.Lock()

        # A lock for access to the SMBus
        self.smbus_lock = threading.Lock()

        # Relay ports and duty cycles
        self.relay = {}
        for r in sorted(RELAY.keys()):
            self.relay[r] = {
                'port': RELAY[r],
                'duty': 0.0
            }

        # Flag to tell relay updater states should be checked
        self.update_relays = False

        # Initialize the database
        con = sqlite3.connect(DATABASE)
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS temperature (
            dt      date,
            id      text,
            temp    real
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS relay (
            dt      date,
            id      text,
            duty    real,
            state   integer
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS environment (
            dt      date,
            pres    real,
            temp    real
        );
        """)
        con.commit()
        con.close()
        os.chown(DATABASE, pwd.getpwnam(WSGI_USER).pw_uid, grp.getgrnam(WSGI_GROUP).gr_gid)
        os.chmod(DATABASE, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)

        self.run = True

        # Initial relay duty values
        self.relay['A']['duty'] = 0.00
        self.relay['B']['duty'] = 0.00
        self.relay['C']['duty'] = 0.00
        self.relay['D']['duty'] = 0.00

        # Start the relay updater
        logging.info('Starting relay updater')
        relay_updater = threading.Thread(target=self.relay_updater)
        relay_updater.start()

        # Start the temperature updater
        logging.info('Starting temperature updater')
        temp_updater = threading.Thread(target=self.temp_updater)
        temp_updater.start()

        # Start the environment updater
        logging.info('Starting environment updater')
        env_updater = threading.Thread(target=self.env_updater)
        env_updater.start()

        # Connect the message handler
        logging.info('Connecting to mesage queue handler')
        Control.check_messages(self)

        logging.info('Waiting for updaters to terminate')
        relay_updater.join()
        temp_updater.join()
        env_updater.join()

        logging.info('Shutting down')
        self.mqueue.close()

        logging.info('Done')

    @staticmethod
    def check_messages(self):

        # Lock the handler and reconnect to the message queue
        self.mqueue_lock.acquire()
        self.mqueue.request_notification((Control.check_messages, self))

        # Clear the message queue
        while self.mqueue.current_messages > 0:

            s, p = self.mqueue.receive()
            s = s.decode().upper().split()

            if s[0] == 'CHECK':
                pass
            elif s[0] == 'STOP':
                self.run = False
            elif s[0] == 'DUTY' and s[1] in self.relay.keys() and s[2].isdecimal():
                d = int(s[2])
                if 0 <= d <= 100:
                    self.relay[s[1]]['duty'] = d / 100
                    self.update_relays = True

            logging.info('Message: %s', ' '.join(s))

        # Unlock the handler
        self.mqueue_lock.release()

    def test(self):
        for i in range(5):
            self.test1('test1-%02d.txt' % i)
            self.test2('test2-%02d.txt' % i)
            self.test1('test3-%02d.txt' % i)

    def test1(self, datafile=None):

        from control.bmp280 import BMP280, BMP280_STATUS_BUSY, BMP280_FILTER_COEFF_OFF
        from control.bmp280 import BMP280_TEMP_NONE, BMP280_TEMP_OS_1X
        from control.bmp280 import BMP280_PRES_OS_1X, BMP280_PRES_OS_2X, BMP280_PRES_OS_4X
        from control.bmp280 import BMP280_MODE_FORCED

        READ_TEMP = BMP280_PRES_OS_2X | BMP280_TEMP_OS_1X
        PRES_ONLY = BMP280_PRES_OS_2X | BMP280_TEMP_NONE

        bmp = BMP280()
        bmp.config(BMP280_FILTER_COEFF_OFF)

        TOTAL_CONV = 2**10
        TEMP_CYCLE = 16

        SLEEP_PRES = 0.0100
        SLEEP_TEMP = 0.0100

        # 170 Hz @ 2X/1X, temp cycle = 64

        logging.info('start')

        data = []
        start = time.time()
        for i in range(0, TOTAL_CONV, TEMP_CYCLE):
            for j in range(TEMP_CYCLE):

                if j == 0:
                    # temperature cycle
                    bmp.control(READ_TEMP | BMP280_MODE_FORCED)
                    while True:
                        time.sleep(SLEEP_TEMP)
                        if bmp.status() & BMP280_STATUS_BUSY == 0:
                            break
                    p, t = bmp.read_sensor(compensate=False)
                    data.append([time.time(), p, t])

                else:
                    # pressure-only cycle
                    bmp.control(PRES_ONLY | BMP280_MODE_FORCED)
                    while True:
                        time.sleep(SLEEP_PRES)
                        if bmp.status() & BMP280_STATUS_BUSY == 0:
                            break
                    p, t = bmp.read_sensor(temp=False, compensate=False)
                    data.append([time.time(), p, None])

        # add a final temperature cycle
        bmp.control(READ_TEMP | BMP280_MODE_FORCED)
        while True:
            time.sleep(SLEEP_TEMP)
            if bmp.status() & BMP280_STATUS_BUSY == 0:
                break
        p, t = bmp.read_sensor(compensate=False)
        data.append([time.time(), p, t])

        end = time.time()

        logging.info('test1 readings: %d', TOTAL_CONV)
        logging.info('test1 time: %.3f', (end - start))
        logging.info('test1 rate: %.1f Hz', (TOTAL_CONV / (end - start)))

        # Interpolate between temperature samples
        head = 0
        for i in range(len(data)):
            if data[i][2] is not None:
                # sample includes temperature
                tail = head
                head = i
                t_start = data[tail][2]
                t_end = data[head][2]
                for j in range(tail, head):
                    int_t = int(round(t_start + (t_end - t_start) * (j - tail) / (head - tail)))
                    data[j][2] = int_t

        # for i in range(len(data)):
        #     print('%4d: %d' % (i, data[i][2]))

        # Compensate the data
        comp = []
        for t, adc_p, adc_t in data:
            pres, temp = bmp.compensate(adc_p, adc_t)

            # Pressure in hPa, temperature in degrees fahrenheit
            comp.append((t, pres / 100, temp * 9 / 5 + 32))

        if datafile:
            with open(datafile, 'w') as f:
                f.write('sample,time,pres,temp\n')
                for i in range(len(comp)):
                    t, pres, temp = comp[i]
                    f.write('%d,%.6f,%.2f,%.2f\n' % (i + 1, t - start, pres, temp))

        logging.info('done')

    def test2(self, datafile=None):

        from control.bmp280 import BMP280, BMP280_STATUS_BUSY, BMP280_FILTER_COEFF_OFF
        from control.bmp280 import BMP280_TEMP_NONE, BMP280_TEMP_OS_1X
        from control.bmp280 import BMP280_PRES_OS_1X, BMP280_PRES_OS_2X, BMP280_PRES_OS_4X
        from control.bmp280 import BMP280_MODE_FORCED

        READ_TEMP = BMP280_PRES_OS_1X | BMP280_TEMP_OS_1X
        PRES_ONLY = BMP280_PRES_OS_1X | BMP280_TEMP_NONE

        bmp = BMP280()
        bmp.config(BMP280_FILTER_COEFF_OFF)

        TOTAL_CONV = 2**16
        TEMP_CYCLE = 128
        SLEEP_TIME = 0.00030

        # 220 Hz @ 1X/1X, temp cycle = 128, sleep = 0.00025

        logging.info('start')

        data = []
        start = time.time()

        # start the first temperature cycle
        bmp.control(READ_TEMP | BMP280_MODE_FORCED)

        for i in range(0, TOTAL_CONV, TEMP_CYCLE):

            for j in range(TEMP_CYCLE):

                # wait for the conversion to finish
                while True:
                    time.sleep(SLEEP_TIME)
                    if bmp.status() & BMP280_STATUS_BUSY == 0:
                        break

                if j == 0:
                    # start next pressure only cycle and read temperature data
                    bmp.control(PRES_ONLY | BMP280_MODE_FORCED)
                    p, t = bmp.read_sensor(compensate=False)
                    data.append([time.time(), p, t])

                elif j == TEMP_CYCLE - 1:
                    # start the next temperature cycle and read pressure only data
                    bmp.control(READ_TEMP | BMP280_MODE_FORCED)
                    p, t = bmp.read_sensor(temp=False, compensate=False)
                    data.append([time.time(), p, None])

                else:
                    # start the next pressure-only cycle and read pressure only data
                    bmp.control(PRES_ONLY | BMP280_MODE_FORCED)
                    p, t = bmp.read_sensor(temp=False, compensate=False)
                    data.append([time.time(), p, None])

        # wait for the final conversion to finish
        while True:
            time.sleep(SLEEP_TIME)
            if bmp.status() & BMP280_STATUS_BUSY == 0:
                break

        # read the final temperature data
        p, t = bmp.read_sensor(compensate=False)
        data.append([time.time(), p, t])

        end = time.time()

        logging.info('test2 readings: %d', TOTAL_CONV)
        logging.info('test2 time: %.3f', (end - start))
        logging.info('test2 rate: %.1f Hz', (TOTAL_CONV / (end - start)))

        # Interpolate between temperature samples
        head = 0
        for i in range(len(data)):
            if data[i][2] is not None:
                # sample includes temperature
                tail = head
                head = i
                t_start = data[tail][2]
                t_end = data[head][2]
                for j in range(tail, head):
                    int_t = int(round(t_start + (t_end - t_start) * (j - tail) / (head - tail)))
                    data[j][2] = int_t

        # for i in range(len(data)):
        #     print('%4d: %s' % (i, str(data[i][2:])))

        # Compensate the data
        comp = []
        for t, adc_p, adc_t in data:
            pres, temp = bmp.compensate(adc_p, adc_t)

            # Pressure in hPa, temperature in degrees fahrenheit
            comp.append((t, pres / 100, temp * 9 / 5 + 32))

        if datafile:
            with open(datafile, 'w') as f:
                f.write('sample,time,pres,temp\n')
                for i in range(len(comp)):
                    t, pres, temp = comp[i]
                    f.write('%d,%.6f,%.2f,%.2f\n' % (i + 1, t - start, pres, temp))

        logging.info('done')
