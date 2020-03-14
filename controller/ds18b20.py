import time
import struct

from controller.ds2482 import DS2482
from controller.ds2482 import DS2482_CONFIG_ACTIVE_PULLUP, DS2482_CONFIG_STRONG_PULLUP
from controller.ds2482 import DS2482_ADDRESS, DS2482_BUSNUM

# DS18B20 ROM commands
DS18B20_ROM_SEARCH              = 0xF0
DS18B20_ROM_READ                = 0x33
DS18B20_ROM_MATCH               = 0x55
DS18B20_ROM_SKIP                = 0xCC
DS18B20_ROM_SEARCH_ALARM        = 0xF0

# DS18B20 function commands

# Convert T starts temperature conversion, strong pullup for parasitic power
#    9-bit resolution: 100ms
#   10-bit resolution: 200ms
#   11-bit resolution: 375ms
#   12-bit resolution: 750ms
DS18B20_FUNCTION_CONVERT_T      = 0x44

# Copy scratchpad memory to EEPROM, 10ms strong pullup for parasitic power
DS18B20_FUNCTION_COPY_SCRATCH   = 0x48

# Other commands do not require strong pullups
DS18B20_FUNCTION_WRITE_SCRATCH  = 0x4E
DS18B20_FUNCTION_READ_SCRATCH   = 0xBE
DS18B20_FUNCTION_RECALL_EEPROM  = 0xB8
DS18B20_FUNCTION_READ_POWER     = 0xB4

# DS18B20 configuration register
DS18B20_CONFIG_9_BIT            = 0x00
DS18B20_CONFIG_10_BIT           = 0x20
DS18B20_CONFIG_11_BIT           = 0x40
DS18B20_CONFIG_12_BIT           = 0x60

DS18B20_CONFIG_RESOLUTION_MASK  = 0x60

# DS18B20 sensors
DS18B20_SENSORS = {
    'A1': {'id': 0x11, 'rom': [0x28, 0x09, 0x89, 0xAB, 0x08, 0x00, 0x00, 0xA8]},
    'B1': {'id': 0x21, 'rom': [0x28, 0xFF, 0xAD, 0xEA, 0x93, 0x16, 0x05, 0x70]},
    'B2': {'id': 0x22, 'rom': [0x28, 0xFF, 0x25, 0x2F, 0x8C, 0x16, 0x03, 0xF5]},
    'B3': {'id': 0x23, 'rom': [0x28, 0xFF, 0xAD, 0x44, 0x94, 0x16, 0x04, 0xE8]},
    'C1': {'id': 0x31, 'rom': [0x28, 0xFF, 0xF3, 0x77, 0x88, 0x16, 0x03, 0x6D]},
    'C2': {'id': 0x32, 'rom': [0x28, 0xFF, 0xD9, 0x05, 0x8C, 0x16, 0x03, 0x19]},
    'C3': {'id': 0x33, 'rom': [0x28, 0xFF, 0xC5, 0x04, 0x8C, 0x16, 0x03, 0xCB]},
    'C4': {'id': 0x34, 'rom': [0x28, 0xFF, 0xA3, 0x78, 0x88, 0x16, 0x03, 0x62]},
    'C5': {'id': 0x35, 'rom': [0x28, 0xFF, 0x63, 0x3A, 0x90, 0x16, 0x05, 0x15]},
    'D1': {'id': 0x41, 'rom': [0x28, 0xE1, 0xEF, 0x76, 0x08, 0x00, 0x00, 0x31]},
    'D2': {'id': 0x42, 'rom': [0x28, 0xAB, 0xDA, 0x76, 0x08, 0x00, 0x00, 0xDD]},
}

CRC_LOOKUP = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53
]


class OneWireDataError(Exception):
    pass


class DS18B20(DS2482):

    def __init__(self, address=DS2482_ADDRESS, busnum=DS2482_BUSNUM):
        super(DS18B20, self).__init__(address, busnum)

    def calc_crc(self, bytes):
        crc = 0
        for b in bytes:
            crc = CRC_LOOKUP[crc ^ b]
        return crc

    def ow_match(self, rom):
        self.ow_write(DS18B20_ROM_MATCH)
        for data in rom:
            self.ow_write(data)

    def parasitic_power(self, rom):
        self.ow_reset()
        self.ow_match(rom)
        self.ow_write(DS18B20_FUNCTION_READ_POWER)
        return False if self.ow_single_bit() else True

    def conversion_time(self, config):
        # DS18B20 conversion time in seconds
        return {
            DS18B20_CONFIG_9_BIT:   0.100,
            DS18B20_CONFIG_10_BIT:  0.200,
            DS18B20_CONFIG_11_BIT:  0.375,
            DS18B20_CONFIG_12_BIT:  0.750,
        }[config & DS18B20_CONFIG_RESOLUTION_MASK]

    def scratchpad(self, rom, data=None):
        # DS18B20 scratchpad memory
        if data and len(data) == 3:

            # Write the alarm triggers and config register
            self.ow_reset()
            self.ow_match(rom)
            self.ow_write(DS18B20_FUNCTION_WRITE_SCRATCH)
            for d in data:
                self.ow_write(d)

        self.ow_reset()
        self.ow_match(rom)
        scratch = []
        self.ow_write(DS18B20_FUNCTION_READ_SCRATCH)
        for i in range(9):
            scratch.append(self.ow_read())

        if self.calc_crc(scratch):
            raise OneWireDataError

        return scratch

    def config(self, rom, config=None):
        # DS18B20 config register
        if config is not None:
            config = self.scratchpad(rom)[2:4] + [config]

        return self.scratchpad(rom, config)[4]

    def save_scratchpad(self, rom):
        self.ow_reset()
        self.ow_match(rom)
        self.master_config(DS2482_CONFIG_ACTIVE_PULLUP | DS2482_CONFIG_STRONG_PULLUP)
        status = self.ow_write(DS18B20_FUNCTION_COPY_SCRATCH)
        time.sleep(0.10)
        self.ow_reset()

    def recall_scratchpad(self, rom):
        self.ow_reset()
        self.ow_match(rom)
        self.ow_write(DS18B20_FUNCTION_COPY_SCRATCH)
        while self.ow_single_bit() == 0:
            continue

    def temperature(self, rom, tc=None, celcius=False):
        if isinstance(rom, str):
            # convert sensor name to a rom address
            rom = DS18B20_SENSORS[rom]['rom']

        if tc is None:
            # get the resolution from the device
            tc = self.conversion_time(self.config(rom))

        self.ow_reset()
        self.ow_match(rom)

        # assume device is running on parasitic power
        self.master_config(DS2482_CONFIG_ACTIVE_PULLUP | DS2482_CONFIG_STRONG_PULLUP)
        self.ow_write(DS18B20_FUNCTION_CONVERT_T)
        time.sleep(tc)

        scratchpad = self.scratchpad(rom)
        temp = struct.unpack('<h', bytes(scratchpad[0:2]))[0] / 2 ** 4
        if not celcius:
            temp = temp * 9 / 5 + 32
        return temp

    # Read ROM - only one device on the bus at a time
    def read_rom(self):
        self.ow_reset()
        rom = []
        self.ow_write(DS18B20_ROM_READ)
        for i in range(8):
            rom.append(self.ow_read())
        if self.calc_crc(rom):
            raise OneWireDataError
        return rom


def test():

    # Point to the configuration register
    device = DS18B20()
    device.master_reset()
    config = device.master_config(DS2482_CONFIG_ACTIVE_PULLUP)
    # print('config: %02x' % config)

    # for s in sorted(DS18B20_SENSORS.keys()):
    #     print('%s: 0x%02X' % (s, device.calc_crc(DS18B20_SENSORS[s]['rom'])))

    # rom = device.read_rom()
    # print('ROM: 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}'.format(*rom))
    # exit(0)

    # sensors = ['A1','B1','B2','B3']
    sensors = ['C%d' % i for i in range(1, 6)]

    config = DS18B20_CONFIG_11_BIT
    tc = device.conversion_time(config)

    sample_rate = 30    # samples per minute

    for sensor in sensors:

        id = DS18B20_SENSORS[sensor]['id']
        rom = DS18B20_SENSORS[sensor]['rom']

        print(('Sensor: %s' % sensor))
        print('ID: %02X' % id)
        print('ROM: 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}, 0x{:02X}'.format(*rom))
        print('tc: %d ms' % int(tc * 1000))

        # Check that device is present and EEPROM has been initialized
        device.recall_scratchpad(rom)
        retries = 2
        while True:
            try:
                scratch = device.scratchpad(rom)
                break
            except OneWireDataError:
                if retries > 0:
                    print('DEVICE NOT RESPONDING, RETRYING...')
                    retries -= 1
                    continue
                print('DEVICE NOT PRESENT.')
                exit(-1)

        if scratch[2:5] != [id, 0, config | 0x1F]:
            print('Initializing EEPROM...')
            device.scratchpad(rom, [id, 0, config])
            device.save_scratchpad(rom)
            device.recall_scratchpad(rom)

        print('Scratchpad: {:02X}-{:02X}-{:02X}-{:02X}-{:02X}-{:02X}-{:02X}-{:02X}-{:02X}'.format(*device.scratchpad(rom)))
        print('Power: %s' % ('parasitic' if device.parasitic_power(rom) else 'external'))
        print()

    print('     %s' % '  '.join(['%5s' % s for s in sensors]))

    i = 0
    while True:

        temps = []
        for sensor in sensors:
            retries = 2
            while True:
                try:
                    t = device.temperature(DS18B20_SENSORS[sensor]['rom'])
                    temps.append(t)
                    break

                except OneWireDataError:
                    if retries > 0:
                        retries -= 1
                    else:
                        print('ERROR reading sensor %s', sensor)
                        exit(-1)

        print('%3d:  %s' % (i + 1, '  '.join(['%5.1f' % t for t in temps])))

        # 6 minute sample period => 10 samples per hour
        # time.sleep(60.0 / sample_rate)
        i += 1

    device.ow_reset()
    device.master_reset()

    print('Done.')