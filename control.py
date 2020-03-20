import sys

from control.control import Control
import control.ds18b20 as ds18b20
import control.mcp23008 as mcp23008


def print_help():
    print('usage: sudo python3 control.py (start|stop|kill)')

if len(sys.argv) == 2 and sys.argv[1] == 'start':
    Control().start()

elif len(sys.argv) == 2 and sys.argv[1] == 'stop':
    Control().stop()

elif len(sys.argv) == 2 and sys.argv[1] == 'kill':
    Control().kill()

elif len(sys.argv) == 2 and sys.argv[1] == 'test':
    Control().test()

elif len(sys.argv) == 2 and sys.argv[1] == 'ds18b20':
    ds18b20.test()

elif len(sys.argv) == 2 and sys.argv[1] == 'mcp23008':
    mcp23008.test()

else:
    print_help()
