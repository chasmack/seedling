import sys

from controller.controller import Controller
import controller.ds18b20 as ds18b20
import controller.mcp23008 as mcp23008


def print_help():
    print('usage: sudo python3 controller.py (start|stop|kill)')

if len(sys.argv) == 2 and sys.argv[1] == 'start':
    Controller().start()

elif len(sys.argv) == 2 and sys.argv[1] == 'stop':
    Controller().stop()

elif len(sys.argv) == 2 and sys.argv[1] == 'kill':
    Controller().kill()

elif len(sys.argv) == 2 and sys.argv[1] == 'test':
    Controller().test()

elif len(sys.argv) == 2 and sys.argv[1] == 'ds18b20':
    ds18b20.test()

elif len(sys.argv) == 2 and sys.argv[1] == 'mcp23008':
    mcp23008.test()

else:
    print_help()
