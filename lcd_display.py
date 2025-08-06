import threading
import time
import random
import string
from RPLCD.i2c import CharLCD
class LCDDisplay:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LCDDisplay, cls).__new__(cls)
                cls._instance.lcd = CharLCD('PCF8574', 0x27, cols=20, rows=4, port=0, dotsize=8, charmap='A02',auto_linebreaks=True, backlight_enabled=True)  # Change address if needed
                print(cls._instance)
                cls._instance.lcd.clear()
                cls._instance.lcd.cursor_pos = (0, 8)  # Move cursor to the first line
                cls._instance.lcd.write_string("ILDS")
                cls._instance.lcd.cursor_pos = (1, 0)  # Move cursor to the first line
                cls._instance.lcd.write_string("BharatFlow Analytics")
                cls._instance.lcd.cursor_pos = (2, 0)  # Move cursor to the first line
                cls._instance.lcd.write_string("P(g) kg/cm2:")
                cls._instance.lcd.cursor_pos = (3, 0)  # Move cursor to the first line
                cls._instance.lcd.write_string("Status:-")
                # cls._instance.lcd.cursor_pos = (3, 0)  # Move cursor to the first line
                # cls._instance.lcd.write_string("AI Status: NORMAL")
                print('Check2')
        return cls._instance       

                          

    def display_message(self,x,y,message):
        
        self.lcd.cursor_pos = (x, y)
        self.lcd.write_string(message)

# Create a static instance to be used everywhere
lcd_instance = LCDDisplay()
