import time

# DS18B20 ROM commands
COMMAND_ROM_SEARCH          = 0xF0
COMMAND_ROM_READ            = 0x33
COMMAND_ROM_MATCH           = 0x55
COMMAND_ROM_SKIP            = 0xCC
COMMAND_ROM_SEARCH_ALARM    = 0xF0

# DS18B20 function commands

# Convert T starts temperature conversion, strong pullup for parasitic power
#    9-bit resolution: 100ms
#   10-bit resolution: 200ms
#   11-bit resolution: 375ms
#   12-bit resolution: 750ms
COMMAND_CONVERT_T           = 0x44

# Copy scratchpad memory to EEPROM, 10ms strong pullup for parasitic power
COMMAND_COPY_SCRATCH        = 0x48

# Other commands do not require strong pullups
COMMAND_WRITE_SCRATCH       = 0x4E
COMMAND_READ_SCRATCH        = 0xBE
COMMAND_RECALL_EEPROM       = 0xB8
COMMAND_READ_POWER          = 0xB4

# Conversion resolution config codes and conversion times (secs)
CONVERT_RES_9_BIT           = 0x1F
CONVERT_RES_10_BIT          = 0x3F
CONVERT_RES_11_BIT          = 0x5F
CONVERT_RES_12_BIT          = 0x7F

CONVERT_TIME = {
    CONVERT_RES_9_BIT:      0.100,
    CONVERT_RES_10_BIT:     0.200,
    CONVERT_RES_11_BIT:     0.375,
    CONVERT_RES_12_BIT:     0.750
}

CONVERT_MASK = {
    CONVERT_RES_9_BIT:      0x07,
    CONVERT_RES_10_BIT:     0x03,
    CONVERT_RES_11_BIT:     0x01,
    CONVERT_RES_12_BIT:     0x00
}

# DS18B20 sensor ROM codes
DS18B20_SENSORS = {
    'A1': [0x28, 0x09, 0x89, 0xAB, 0x08, 0x00, 0x00, 0xA8],
    'B1': [0x28, 0xFF, 0xAD, 0xEA, 0x93, 0x16, 0x05, 0x70],
    'B2': [0x28, 0xFF, 0x25, 0x2F, 0x8C, 0x16, 0x03, 0xF5],
    'B3': [0x28, 0xFF, 0xAD, 0x44, 0x94, 0x16, 0x04, 0xE8],
    'C1': [0x28, 0xFF, 0xF3, 0x77, 0x88, 0x16, 0x03, 0x6D],
    'C2': [0x28, 0xFF, 0xD9, 0x05, 0x8C, 0x16, 0x03, 0x19],
    'C3': [0x28, 0xFF, 0xC5, 0x04, 0x8C, 0x16, 0x03, 0xCB],
    'C4': [0x28, 0xFF, 0xA3, 0x78, 0x88, 0x16, 0x03, 0x62],
    'C5': [0x28, 0xFF, 0x63, 0x3A, 0x90, 0x16, 0x05, 0x15],
    'D1': [0x28, 0xE1, 0xEF, 0x76, 0x08, 0x00, 0x00, 0x31],
    'D2': [0x28, 0xAB, 0xDA, 0x76, 0x08, 0x00, 0x00, 0xDD],
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


class DS18B20:

    @staticmethod
    def calc_crc(byte_data):
        crc = 0
        for b in byte_data:
            crc = CRC_LOOKUP[crc ^ b]
        return crc

    def __init__(self, onewire, rom=None, convert_res=CONVERT_RES_11_BIT):
        self._ow = onewire
        self._rom = rom
        self._parasitic = self.parasitic_power
        self.set_resolution(convert_res)

    def select(self):
        self._ow.wait_ready()
        self._ow.reset()
        if self._rom:
            self._ow.write_byte(COMMAND_ROM_MATCH)
            for b in self._rom:
                self._ow.write_byte(b)
        else:
            self._ow.write_byte(COMMAND_ROM_SKIP)

    def set_resolution(self, convert_res):
        scratch = self.scratchpad[2:5]
        scratch[2] = convert_res
        self.scratchpad = scratch
        self.convert_res = convert_res

    @property
    def parasitic_power(self):
        self._ow.reset()
        self._ow.write_byte(COMMAND_ROM_SKIP)
        self._ow.write_byte(COMMAND_READ_POWER)
        return not self._ow.single_bit()

    @property
    def temperature(self):
        t = int.from_bytes(self.scratchpad[0:2], byteorder='little', signed=True)
        return (t & ~CONVERT_MASK[self.convert_res]) / 16.0

    @property
    def scratchpad(self):
        self.select()
        self._ow.write_byte(COMMAND_READ_SCRATCH)
        buf = bytearray(9)
        for i in range(9):
            buf[i] = self._ow.read_byte()
        if DS18B20.calc_crc(buf):
            raise OneWireDataError('Bad CRC: %s' % ' '.join(hex(i) for i in buf))
        return buf

    @scratchpad.setter
    def scratchpad(self, data):
        self.select()
        self._ow.write_byte(COMMAND_WRITE_SCRATCH)
        for i in range(3):
            self._ow.write_byte(data[i])

    def copy_scratchpad(self):
        self.select()
        if self._parasitic:
            self._ow.write_byte(COMMAND_COPY_SCRATCH, strong_pullup=True, busy=0.010)
        else:
            self._ow.write_byte(COMMAND_COPY_SCRATCH)

    def recall_scratchpad(self):
        self.select()
        self._ow.write_byte(COMMAND_RECALL_EEPROM)
        while self._ow.single_bit() == 0:
            continue

    def convert_t(self):
        self.select()
        if self._parasitic:
            self._ow.write_byte(COMMAND_CONVERT_T, strong_pullup=True, busy=CONVERT_TIME[self.convert_res])
        else:
            self._ow.write_byte(COMMAND_CONVERT_T)

    def read_rom(self):
        """Read the 8-byte rom code from a SINGLE DEVICE"""
        buf = bytearray(8)
        self.select()
        self._ow.write_byte(COMMAND_ROM_READ)
        for i in range(8):
            buf[i] = self._ow.read_byte()
        if DS18B20.calc_crc(buf):
            raise OneWireDataError
        return buf

def to_fahrenheit(t):
    return t * 1.8 + 32.0

if __name__ == '__main__':

    import board
    import busio
    from control.ds2482 import DS2482

    i2c = busio.I2C(board.SCL, board.SDA)
    onewire = DS2482(i2c, active_pullup=True)

    tmp = {}
    sensor_ids = ('C1', 'C2', 'C3', 'C4', 'C5')
    for id in sensor_ids:
        tmp[id] = DS18B20(onewire, rom=DS18B20_SENSORS[id], convert_res=CONVERT_RES_11_BIT)

    for id in sensor_ids:
        tmp[id].convert_t()
        print('%s temp: %.2f C  (%0.1f F)' % (id, tmp[id].temperature, to_fahrenheit(tmp[id].temperature)))
        # print('%s temp: %.1f F' % (id, to_fahrenheit(sensor[id].temperature)))
