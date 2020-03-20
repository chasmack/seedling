import time

import adafruit_bus_device.i2c_device as i2c_device

# Device i2c address
MCP23008_ADDRESS = 0x22

# 8-bit registers
MCP23008_IODIR      = 0x00      # IO direction, 1 => input
MCP23008_IPOL       = 0x01      # Input polarity, 1 => invert
MCP23008_GPINTEN    = 0x02      # Interrupt on change, 1 => enable
MCP23008_DEFVAL     = 0x03      # Default compare for interrupt on change
MCP23008_INTCON     = 0x04      # Interrupt control, 1 => use default value
MCP23008_IOCON      = 0x05      # Configuration register, see below
MCP23008_GPPU       = 0x06      # Input pullup, 1 => internal 100k pullup in input
MCP23008_INTF       = 0x07      # Interrupt flag, read 1 for pin interrupt
MCP23008_INTCAP     = 0x08      # Interrupt capture, saved state of GPIO at time of interrupt
MCP23008_GPIO       = 0x09      # GPIO, read from pin, write to latch
MCP23008_OLAT       = 0x0A      # Output latch

# Configuration register bits
MCP23008_IOCON_SEQOP    = 0x20      # Sequential addressing, 0 => increment address pointer
MCP23008_IOCON_DISSLW   = 0x10      # Slew rate control, 0 => enable output slew rate control
MCP23008_IOCON_ODR      = 0x04      # Open-drain interrupt output, 1 => open-drain (ignore INTPOL)
MCP23008_IOCON_INTPOL   = 0x02      # Interrupt polarity, 1 => active high

# Port bit names
PORT_A0 = 0x01
PORT_A1 = 0x02
PORT_A2 = 0x04
PORT_A3 = 0x08
PORT_A4 = 0x10
PORT_A5 = 0x20
PORT_A6 = 0x40
PORT_A7 = 0x80

class MCP23008(object):

    def __init__(self, i2c, address=MCP23008_ADDRESS):
        self.gpio = i2c_device.I2CDevice(i2c, address)
        self.gpio.write(bytes([MCP23008_IOCON, 0]))

    def input(self):
        buf  = bytearray([MCP23008_GPIO])
        self.gpio.write_then_readinto(buf, buf)
        return buf[0]

    def olat(self, mask, data=None):
        buf = bytearray([MCP23008_OLAT,  0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        if not data is None:
            buf[1] = ((buf[1] & ~mask) | (data & mask)) & 0xFF
            self.gpio.write(buf)
        return buf[1] & mask

    def output_high(self, mask):
        buf = bytearray([MCP23008_OLAT,  0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        buf[1] |= mask
        self.gpio.write(buf)
        return self

    def output_low(self, mask):
        buf = bytearray([MCP23008_OLAT, 0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        buf[1] &= ~mask
        self.gpio.write(buf)
        return self

    def config_invert(self, mask, state=True):
        buf = bytearray([MCP23008_IPOL, 0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        if state:
            buf[1] |= mask
        else:
            buf[1] &= ~mask
        self.gpio.write(buf)
        return self

    def config_pullup(self, mask, state=True):
        buf = bytearray([MCP23008_GPPU, 0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        if state:
            buf[1] |= mask
        else:
            buf[1] &= ~mask
        self.gpio.write(buf)
        return self

    def config_input(self, mask):
        buf = bytearray([MCP23008_IODIR, 0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        buf[1]|= mask
        self.gpio.write(buf)
        return self

    def config_output(self, mask):
        buf = bytearray([MCP23008_IODIR, 0x00])
        self.gpio.write_then_readinto(buf, buf, out_end=1, in_start=1)
        buf[1] &= (~mask & 0xFF)
        self.gpio.write(buf)
        return self


if __name__ == '__main__':
    import board
    import busio

    RELAY_A = PORT_A0
    RELAY_B = PORT_A1
    RELAY_C = PORT_A2
    RELAY_D = PORT_A3

    RELAYS = RELAY_A | RELAY_B | RELAY_C | RELAY_D

    LED = PORT_A4

    # short kill sense to kill bias to end loop
    KILL_SENSE = PORT_A7
    KILL_BIAS = PORT_A6

    i2c = busio.I2C(board.SCL, board.SDA)
    mcp = MCP23008(i2c, address=MCP23008_ADDRESS)

    # led off (low)
    mcp.config_output(LED).output_low(LED)

    # configure A7 as the kill swithch
    mcp.config_input(KILL_SENSE).config_invert(KILL_SENSE).config_pullup(KILL_SENSE)
    mcp.config_output(KILL_BIAS).config_output(KILL_BIAS).output_low(KILL_BIAS)

    # relays off (high), configure as outputs
    mcp.output_high(RELAYS).config_output(RELAYS)

    n = 0
    done = 0
    while True:

        if mcp.input() & KILL_SENSE:
            print('pins: %02x' % mcp.input())
            done = 1

        # relays are active low
        relays = ~mcp.olat(RELAYS) & RELAYS
        relays = RELAY_A if relays == 0 else (relays << 1) & RELAYS
        mcp.olat(RELAYS, ~relays)
        print('relays: %02x, olat: %02x' % (relays, mcp.olat(RELAYS)))

        time.sleep(0.5)

        if done and (~mcp.olat(RELAYS) & RELAYS) == 0:
            break

        n += 1
        if n == 50:
            done = 1

    # reset the device
    mcp.output_high(RELAYS)  # relays off (high)
    mcp.config_input(0xFF)  # all inputs
