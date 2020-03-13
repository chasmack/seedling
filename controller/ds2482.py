import time

import Adafruit_GPIO.I2C as I2C

# Device i2c address
DS2482_ADDRESS = 0x18
DS2482_BUSNUM = 1

# DS2482 device commands
DS2482_COMMAND_DEVICE_RESET         = 0xF0
DS2482_COMMAND_SET_READ_POINTER     = 0xE1
DS2482_COMMAND_WRITE_CONFIG         = 0xD2
DS2482_COMMAND_1W_RESET             = 0xB4
DS2482_COMMAND_1W_SINGLE_BIT        = 0x87
DS2482_COMMAND_1W_WRITE_BYTE        = 0xA5
DS2482_COMMAND_1W_READ_BYTE         = 0x96
DS2482_COMMAND_1W_TRIPLET           = 0x78

# DS2482 read pointer codes
DS2482_POINTER_STATUS               = 0xF0
DS2482_POINTER_DATA                 = 0xE1
DS2482_POINTER_CONFIG               = 0xC3

# DS2482 configuration register
DS2482_CONFIG_ACTIVE_PULLUP         = 0x01
DS2482_CONFIG_STRONG_PULLUP         = 0x04
DS2482_CONFIG_OVERDRIVE             = 0x08

# DS2482 status register
DS2482_STATUS_BUSY                  = 0x01
DS2482_STATUS_PRESENCE_PULSE        = 0x02
DS2482_STATUT_SHORT_DETECTED        = 0x04
DS2482_STATUS_LOGIC_LEVEL           = 0x08
DS2482_STATUS_DEVICE_RESET          = 0x10
DS2482_STATUS_SINGLE_BIT_RESULT     = 0x20
DS2482_STATUS_TRIPLET_BIT           = 0x40
DS2482_STATUS_BRANCH_TAKEN          = 0x80

class DS2482(I2C.Device):

    def __init__(self, address=DS2482_ADDRESS, busnum=DS2482_BUSNUM):
        super(DS2482, self).__init__(address, busnum)

    def master_reset(self):
        self.writeRaw8(DS2482_COMMAND_DEVICE_RESET)

    def master_status(self):
        self.write8(DS2482_COMMAND_SET_READ_POINTER, DS2482_POINTER_STATUS)
        return self.readRaw8()

    def master_config(self, config=None):
        if config is not None:
            self.write8(DS2482_COMMAND_WRITE_CONFIG, (config & 0x0F) | ((~config << 4) & 0xF0))
        else:
            self.write8(DS2482_COMMAND_SET_READ_POINTER, DS2482_POINTER_CONFIG)
        return self.readRaw8()

    def ow_wait_ready(self):
        self.write8(DS2482_COMMAND_SET_READ_POINTER, DS2482_POINTER_STATUS)
        status = self.readRaw8()
        while self.readRaw8() & DS2482_STATUS_BUSY:
            time.sleep(100e-6)
            status = self.readRaw8()
        return status

    def ow_reset(self):
        self.writeRaw8(DS2482_COMMAND_1W_RESET)
        return self.ow_wait_ready()

    def ow_single_bit(self, bit=1):
        self.write8(DS2482_COMMAND_1W_SINGLE_BIT, 0x80 if bit else 0x00)
        status = self.ow_wait_ready()
        return 1 if status & DS2482_STATUS_SINGLE_BIT_RESULT else 0

    def ow_write(self, data):
        self.write8(DS2482_COMMAND_1W_WRITE_BYTE, data)
        return self.ow_wait_ready()

    def ow_read(self):
        self.writeRaw8(DS2482_COMMAND_1W_READ_BYTE)
        self.ow_wait_ready()
        self.write8(DS2482_COMMAND_SET_READ_POINTER, DS2482_POINTER_DATA)
        return self.readRaw8()

    def ow_triplet(self, dir):
        self.write8(DS2482_COMMAND_1W_TRIPLET, 0x80 if dir else 0x00)
        return self.ow_wait_ready()


if __name__ == '__main__':

    device = DS2482()
    config = device.master_config(DS2482_CONFIG_ACTIVE_PULLUP)
    print('config: %02x' % config)
