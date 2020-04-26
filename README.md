## Seedling Control

A bang-bang temperature controller for seedling heat mats. 

Implements four independent channels of control. 
Each channel uses a DS18B20 1-Wire temperature sensor for feedback. 
Additional DS18B20 sensors can be configured to monitor auxiliary temperatures. 
A web interface is provided to monitor and adjust temperatures. 
The top level monitor process runs as a SYSTEMD(1) service. 

### Hardware

The system runs on a Raspberry Pi Zero. The Pi's I2C port controls an MCP23008 8-bit I/O expander 
and a DS2482-100 1-wire master. The I/O expander drives a four channel opto-coupled relay module. 
The 1-wire master controls four DS18B20 temperature sensors running in parasitic power mode. 
Additional DS18B20 sensors can be added. The I/O expander and I2C master both run on +5v power 
to reduce load on the Pi's 3v3 supply. An Adafruit BSS138 4-channel bi-directional level shifter 
is used to convert the Pi's 3v3 I2C bus to run with the 5v I/O.

### Control Process

A simple control loop reads the DS18B20 temperature sensors and controls the relay ports. 
A command queue allows control channels to be enabled/disabled and the setpoint adjusted. 
A response queue acknowledges commands and provides system status. 

### Web User Interface

A simple Flask web app displays the system status and allows control channels to be 
enabled/disabled and the setpoint adjusted. 

![Seedling Web UI](https://github.com/chasmack/seedling/blob/master/docs/screenshot.png "Seedling Web UI")
