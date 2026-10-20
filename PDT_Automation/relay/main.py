import sys
import uselect
from machine import Pin

# Map the 4 channels to GPIO 4, 5, 6, and 7
# Configured as OPEN_DRAIN: 0 = Pulled LOW (ON), 1 = Floating (OFF)
relays = {
    1: Pin(4, Pin.OPEN_DRAIN, value=1),
    2: Pin(5, Pin.OPEN_DRAIN, value=1),
    3: Pin(6, Pin.OPEN_DRAIN, value=1),
    4: Pin(7, Pin.OPEN_DRAIN, value=1)
}

# Onboard status LED
blue_led = Pin(8, Pin.OUT, value=1)

# Non-blocking serial reader setup
spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)

print("ESP32_4CH_READY")

while True:
    if spoll.poll(50):
        raw_cmd = sys.stdin.readline().strip()
        
        # Command format: R<channel>_<state>, e.g. R1_ON, R2_OFF, ALL_ON, ALL_OFF
        if raw_cmd.startswith("R") and "_" in raw_cmd:
            parts = raw_cmd.split("_")
            try:
                ch = int(parts[0][1:])
                state = parts[1]
                if ch in relays:
                    if state == "ON":
                        relays[ch].value(0)
                        print("STATUS:R{}_ON".format(ch))
                    elif state == "OFF":
                        relays[ch].value(1)
                        print("STATUS:R{}_OFF".format(ch))
            except ValueError:
                pass
                
        elif raw_cmd == "ALL_ON":
            for r in relays.values():
                r.value(0)
            blue_led.value(0)
            print("STATUS:ALL_ON")
            
        elif raw_cmd == "ALL_OFF":
            for r in relays.values():
                r.value(1)
            blue_led.value(1)
            print("STATUS:ALL_OFF")