import logging
import time

# Save a logging file
LOGFILE = None
# LOGLEVEL = logging.DEBUG
LOGLEVEL = logging.INFO

# BMP280 default address.
BMP280_I2C_ADDR           = 0x76

# Control register
BMP280_MODE_SLEEP       = 0x00          # Power modes mode[1:0]
BMP280_MODE_FORCED      = 0x01
BMP280_MODE_NORMAL      = 0x03
BMP280_MODE_MASK        = 0x03

BMP280_PRES_NONE        = 0x00          # Pressure sampling osrs_p[2:0]
BMP280_PRES_OS_1X       = 0x01 << 2
BMP280_PRES_OS_2X       = 0x02 << 2
BMP280_PRES_OS_4X       = 0x03 << 2
BMP280_PRES_OS_8X       = 0x04 << 2
BMP280_PRES_OS_16X      = 0x07 << 2
BMP280_PRES_MASK        = 0x07 << 2

BMP280_TEMP_NONE        = 0x00          # Temperature sampling osrs_t[2:0]
BMP280_TEMP_OS_1X       = 0x01 << 5
BMP280_TEMP_OS_2X       = 0x02 << 5
BMP280_TEMP_OS_4X       = 0x03 << 5
BMP280_TEMP_OS_8X       = 0x04 << 5
BMP280_TEMP_OS_16X      = 0x07 << 5
BMP280_TEMP_MASK        = 0x07 << 5

BMP280_OS_MODE_ULTRA_LOW_POWER = {
    'CONTROL': BMP280_PRES_OS_1X | BMP280_TEMP_OS_1X, 'CONVERSION_TIME': 0.0064
}
BMP280_OS_MODE_LOW_POWER = {
    'CONTROL': BMP280_PRES_OS_2X | BMP280_TEMP_OS_1X, 'CONVERSION_TIME': 0.0087
}
BMP280_OS_MODE_STANDARD_RESOLUTION = {
    'CONTROL': BMP280_PRES_OS_4X | BMP280_TEMP_OS_1X, 'CONVERSION_TIME': 0.0133
}
BMP280_OS_MODE_HIGH_RESOLUTION = {
    'CONTROL': BMP280_PRES_OS_8X | BMP280_TEMP_OS_1X, 'CONVERSION_TIME': 0.0225
}
BMP280_OS_MODE_ULTRA_HIGH_RESOLUTION = {
    'CONTROL': BMP280_PRES_OS_16X | BMP280_TEMP_OS_2X, 'CONVERSION_TIME': 0.0432
}

# Configuration register
BMP280_SPI3W_EN         = 0x01          # 1 => enable 3-wire SPI interface

BMP280_FILTER_COEFF_OFF = 0x00          # IIR Filter coefficients filter[2:0]
BMP280_FILTER_COEFF_2   = 0x01 << 2     # 2 samples to 75% step response
BMP280_FILTER_COEFF_4   = 0x02 << 2     # 5 samples to 75% step response
BMP280_FILTER_COEFF_8   = 0x03 << 2     # 11 samples to 75% step response
BMP280_FILTER_COEFF_16  = 0x04 << 2     # 22 samples to 75% step response
BMP280_FILTER_MASK      = 0x07 << 2

BMP280_STANDBY_0P5      = 0x00          # Standby time (ms) t_sb[2:0]
BMP280_STANDBY_62P5     = 0x01 << 5
BMP280_STANDBY_125      = 0x02 << 5
BMP280_STANDBY_250      = 0x03 << 5
BMP280_STANDBY_500      = 0x04 << 5
BMP280_STANDBY_1000     = 0x05 << 5
BMP280_STANDBY_2000     = 0x06 << 5
BMP280_STANDBY_4000     = 0x07 << 5
BMP280_STANDBY_MASK     = 0x07 << 5

# BMP280 Registers
BMP280_CHIP_ID      = 0xD0  # Chip ID => 0x58
BMP280_RESET        = 0xE0  # Reset 0xB6 => power on reset
BMP280_STATUS       = 0xF3  # 7,6,5,4 reserved, 3 measuring, 2,1 reserved, 0 nvm data update
BMP280_CONTROL      = 0xF4  # 7,6,5 osrs_t, 4,3,2 osrs_p, 1,0 mode
BMP280_CONFIG       = 0xF5  # 7,6,5 t_sb, 4,3,2 filter, 1 reserved, 0 spi3w_en
BMP280_DATA         = 0xF7  # Starting address for six byte burst read
BMP280_PRES_DATA    = 0xF7  # Starting address for three byte pressure only burst read
BMP280_PRES_MSB     = 0xF7  # Individual pressure data registers - see Sec. 3.9
BMP280_PRES_LSB     = 0xF8
BMP280_PRES_XLSB    = 0xF9
BMP280_TEMP_DATA    = 0xFA  # Starting address for three byte temperature only burst read
BMP280_TEMP_MSB     = 0xFA  # Individual temperature data registers - see Sec. 3.9
BMP280_TEMP_LSB     = 0xFB
BMP280_TEMP_XLSB    = 0xFC

# Compensation parameters (16-bits, LSB first)
BMP280_DIG_T1       = 0x88  # Unsigned
BMP280_DIG_T2       = 0x8A  # Signed
BMP280_DIG_T3       = 0x8C  # Signed
BMP280_DIG_P1       = 0x8E  # Unsigned
BMP280_DIG_P2       = 0x90  # Signed
BMP280_DIG_P3       = 0x92  # Signed
BMP280_DIG_P4       = 0x94  # Signed
BMP280_DIG_P5       = 0x96  # Signed
BMP280_DIG_P6       = 0x98  # Signed
BMP280_DIG_P7       = 0x9A  # Signed
BMP280_DIG_P8       = 0x9C  # Signed
BMP280_DIG_P9       = 0x9E  # Signed

# Status register
BMP280_STATUS_BUSY  = 0x08  # busy with conversions, 1 => busy
BMP280_STATUS_UPDATE = 0x01  # busy updating NVM data, 1 => busy

class BMP280(object):

    def __init__(self, address=BMP280_I2C_ADDR, i2c=None, **kwargs):

        # Initialize logging
        self._logger = logging.getLogger('BMP280')
        self._logger.setLevel(LOGLEVEL)
        formatter = logging.Formatter(
            '%(levelname)s %(asctime)s %(message)s',
            '%Y-%m-%d %H:%M:%S'
        )

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self._logger.addHandler(ch)

        if LOGFILE:
            fh = logging.FileHandler(LOGFILE)
            fh.setLevel(LOGLEVEL)
            fh.setFormatter(formatter)
            self._logger.addHandler(fh)

        # Create I2C device.
        if i2c is None:
            import Adafruit_GPIO.I2C as I2C
            i2c = I2C
        self._device = i2c.get_i2c_device(address, **kwargs)

        # Check device ID and issue reset
        assert self.chip_id() == 0x58
        self.reset()

        # Load calibration values.
        self.load_calibration()

    def load_calibration(self, sample=False):

        if sample:
            self.dig_t1 = 27504
            self.dig_t2 = 26435
            self.dig_t3 = -1000
            self.dig_p1 = 36477
            self.dig_p2 = -10685
            self.dig_p3 = 3024
            self.dig_p4 = 2855
            self.dig_p5 = 140
            self.dig_p6 = -7
            self.dig_p7 = 15500
            self.dig_p8 = -14600
            self.dig_p9 = 6000

        else:
            self.dig_t1 = self._device.readU16(BMP280_DIG_T1)   # UINT16
            self.dig_t2 = self._device.readS16(BMP280_DIG_T2)   # INT16
            self.dig_t3 = self._device.readS16(BMP280_DIG_T3)   # INT16
            self.dig_p1 = self._device.readU16(BMP280_DIG_P1)   # UINT16
            self.dig_p2 = self._device.readS16(BMP280_DIG_P2)   # INT16
            self.dig_p3 = self._device.readS16(BMP280_DIG_P3)   # INT16
            self.dig_p4 = self._device.readS16(BMP280_DIG_P4)   # INT16
            self.dig_p5 = self._device.readS16(BMP280_DIG_P5)   # INT16
            self.dig_p6 = self._device.readS16(BMP280_DIG_P6)   # INT16
            self.dig_p7 = self._device.readS16(BMP280_DIG_P7)   # INT16
            self.dig_p8 = self._device.readS16(BMP280_DIG_P8)   # INT16
            self.dig_p9 = self._device.readS16(BMP280_DIG_P9)   # INT16

    def reset(self):
        self._device.write8(BMP280_RESET, 0xB6)

    def chip_id(self):
        data = self._device.readU8(BMP280_CHIP_ID)
        self._logger.debug('chip id: 0x%02X', data)
        return data

    def status(self):
        return self._device.readU8(BMP280_STATUS)

    def control(self, data=None):
        if data is not None:
            self._device.write8(BMP280_CONTROL, data)
        return self._device.readU8(BMP280_CONTROL)

    def config(self, data=None):
        if data is not None:
            self._device.write8(BMP280_CONFIG, data)
        data = self._device.readU8(BMP280_CONFIG)
        self._logger.debug('config: 0x%02X', data)
        return data

    def os_mode(self, mode):
        self._os_mode = mode
        data = self.control(self._os_mode['CONTROL'] | BMP280_MODE_SLEEP)
        self._logger.debug('oversample: 0x%02X', data)
        return data

    def convert(self, mode, sleep=True):
        data = self.control(self._os_mode['CONTROL'] | mode & BMP280_MODE_MASK)
        while sleep and (self.status() & BMP280_STATUS_BUSY):
            time.sleep(self._os_mode['CONVERSION_TIME'])
        self._logger.debug('convert: 0x%02X', data)
        return data

    def read_sensor(self, pres=True, temp=True, compensate=True):

        if temp and pres:
            # Read uncompensated pressure and temperature
            data = self._device.readList(BMP280_DATA, 6)
            adc_p = data[0] << 12 | data[1] << 4 | data[2] >> 4
            adc_t = data[3] << 12 | data[4] << 4 | data[5] >> 4
            # self._logger.debug('raw pres: %d raw temp: %d', adc_p, adc_t)
        elif pres:
            # Read uncompensated pressure
            data = self._device.readList(BMP280_PRES_DATA, 3)
            adc_p = data[0] << 12 | data[1] << 4 | data[2] >> 4
            adc_t = None
            # self._logger.debug('raw pres: %d raw temp: None', adc_p)
        elif temp:
            # Read uncompensated temperature
            data = self._device.readList(BMP280_TEMP_DATA, 3)
            adc_p = None
            adc_t = data[0] << 12 | data[1] << 4 | data[2] >> 4
            # self._logger.debug('raw pres: None raw temp: %d', adc_t)
        else:
            adc_p = None
            adc_t = None

        if pres and temp and compensate:
            # Compensate pressure and temperature
            return self.compensate(adc_p, adc_t)
        else:
            # Return uncompensated values
            return adc_p, adc_t

    def compensate(self, adc_p, adc_t):
        # Compensate temperature
        self._logger.debug('temp comp')
        var1 = (adc_t / 16384 - self.dig_t1 / 1024) * self.dig_t2
        self._logger.debug('var1: %f', var1)
        var2 = (adc_t / 131072 - self.dig_t1 / 8192.0) * (adc_t / 131072 - self.dig_t1 / 8192) * self.dig_t3
        self._logger.debug('var2: %f', var2)
        t_fine = var1 + var2
        self._logger.debug('t_fine: %f', t_fine)

        # Compensate pressure
        self._logger.debug('pres comp')
        var1 = t_fine / 2 - 64000
        self._logger.debug('var1: %f', var1)
        var2 = var1 ** 2 * self.dig_p6 / 32768
        self._logger.debug('var2: %f', var2)
        var2 += var1 * self.dig_p5 * 2
        self._logger.debug('var2: %f', var2)
        var2 = var2 / 4 + self.dig_p4 * 65536
        self._logger.debug('var2: %f', var2)
        var1 = (self.dig_p3 * var1 ** 2 / 524288 + self.dig_p2 * var1) / 524288
        self._logger.debug('var1: %f', var1)
        var1 = (1 + var1 / 32768) * self.dig_p1
        self._logger.debug('var1: %f', var1)
        if var1 == 0: return None  # avoid division by zero
        p = 1048576 - adc_p
        self._logger.debug('p: %f', p)
        p = (p - var2 / 4096) * 6250 / var1
        self._logger.debug('p: %f', p)
        var1 = self.dig_p9 * p ** 2 / 2147483648
        self._logger.debug('var1: %f', var1)
        var2 = p * self.dig_p8 / 32768
        self._logger.debug('var2: %f', var2)
        P = p + (var1 + var2 + self.dig_p7) / 16    # pressure in Pa
        T = (t_fine * 5 + 128) / 25600  # temperature in degrees C

        return P, T

if __name__ == '__main__':

    bmp = BMP280()

    bmp.load_calibration(sample=True)
    print('sample calibration data -')
    print('pres: %.2f Pa temp: %.2f' % bmp.compensate(415148, 519888))

    bmp.load_calibration()
    bmp.os_mode(BMP280_OS_MODE_HIGH_RESOLUTION)
    bmp.config(BMP280_FILTER_COEFF_4)
    print('High resolution conversion.')
    while True:
        bmp.convert(BMP280_MODE_FORCED)
        pres, temp = bmp.read_sensor()
        print('pres: %.2f hPa temp: %.2f ' % (pres / 100, temp * 9 / 5 + 32))
        time.sleep(1.0)
