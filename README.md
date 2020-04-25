# Seedling Control

A bang-bang temperature controller for seedling heat mats. 

Implements four independent channels of control. 
Each channel uses a DS18B20 1-Wire temperature sensor for feedback. 
Additional DS18B20 sensors can be configured to monitor auxiliary temperatures. 
A web interface is provided to monitor and adjust temperatures. 
The top level monitor process runs as a SYSTEMD(1) service. 
