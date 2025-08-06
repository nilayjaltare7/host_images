import numpy as np
from decimal import Decimal, ROUND_HALF_UP
import time
import csv
import os
import logging
from board import SCL, SDA
from busio import I2C
# import adafruit_ads1x15.ads1015 as ADS
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from datetime import datetime
import pytz
import json
from dotenv import load_dotenv, set_key
from queue_server import QueueManager
import re
import threading
from collections import deque
from lcd_display import lcd_instance


# Load environment variables from .env file
load_dotenv()

manager = QueueManager(address=(os.getenv('QUEUE_HOST'), int(os.getenv('QUEUE_PORT'))), authkey=os.getenv('AUTH_KEY').encode())
manager.connect()

# Configure logging
log_dir = os.getenv('LOG_DIRECTORY')
log_file = os.getenv('LOG_FILE_ADC')
os.makedirs(log_dir, exist_ok=True)
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level, logging.INFO)

logger = logging.getLogger(os.getenv('LOGGER_ADC'))
logger.setLevel(log_level)
file_handler_adc = logging.FileHandler(os.path.join(log_dir, log_file))
file_handler_adc.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(file_handler_adc)
samples_lcd=[]
def get_last_batch_number(backup_adc_batches):
    batch_files=[f for f in os.listdir(backup_adc_batches) if re.match(r"BFA1_Batch(\d+)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv", f)]
    batch_numbers = [int(re.search(r"BFA1_Batch(\d+)", file).group(1)) for file in batch_files]
    return max(batch_numbers) if batch_numbers else 0


try:
    # Initialize I2C
    logger.debug("Initializing I2C bus...")
    i2c = I2C(SCL, SDA)
    logger.info("I2C bus initialized successfully.")



    # Initialize ADC (ADS1015)
    logger.debug("Initializing ADS1015...")
    ads = ADS.ADS1115(i2c, data_rate=475, gain = 1)
    chan = AnalogIn(ads, ADS.P1)
    logger.info("ADS1015 initialized successfully.")
    

    # Initialize LCD
    logger.debug("Initializing LCD...")

    logger.info("LCD initialized successfully.")
    
   

    # Batch and sampling setup
    backup_adc_batches=os.getenv('FILE_DIRECTORY_ADC_BATCHES_BACKUP')
    output_folder = os.getenv('FILE_DIRECTORY_ADC_BATCHES')
    batch_number = get_last_batch_number(backup_adc_batches) + 1
    if not os.path.exists(backup_adc_batches):
        os.makedirs(backup_adc_batches)
        logger.info(f"Output folder created: {backup_adc_batches}")

    batch_size = int(os.getenv('BATCH_SIZE'))
    sampling_interval = float(os.getenv('SAMPLING_RATE'))
    ist_tz = pytz.timezone(os.getenv('TIMEZONE'))

    # Moving average setup

    moving_avg_queue = deque(maxlen=100)
    print(moving_avg_queue)
    lcd_update_interval = 3

    def voltage_to_pressure(voltage,resistance):
        current_mA = (voltage/ resistance) * 1000
        I_min,I_max = 4,20  # Current Range in mA
        P_min,P_max = 0,100  #Pressure Range in bar
        pressure_bar = ((current_mA - I_min) * (P_max - P_min)) / (I_max - I_min) + P_min
        pressure_kg_cm2 = pressure_bar * 1.0197

        return pressure_kg_cm2
  
        

 

    def update_lcd(moving_avg):
        """Update the LCD with the current moving average."""
        moving_avg = max(moving_avg, 0.00)
        lcd_instance.display_message(2, 12,"     " )
        lcd_instance.display_message(2, 13,f"{moving_avg:.2f}" )  # Move cursor to the second line 
     
        

    def process_moving_average():
        """Process the moving average calculation and LCD update."""
        
        while True:
            if len(samples_lcd) > 100:
                
                moving_avg = np.sum(samples_lcd[-100:]) / 100
                print(moving_avg)
                update_lcd(moving_avg)
            time.sleep(lcd_update_interval)

        

    # Start the thread for moving average and LCD updates   
    threading.Thread(target=process_moving_average, daemon=True).start()
    

    # Main data collection loop
    while True:
        try:
            logger.info(f"Starting collection for batch {batch_number}.")
            samples = []
            start_time = time.time()
            
            for i in range(batch_size):
                current_time = time.time()
                # formatted_timestamp = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]

                voltage2 = chan.voltage
                voltage_float = float(voltage2)
                resistor_value = int(os.getenv('RESISTOR_VALUE'))
                pressure_kg_cm2 = voltage_to_pressure(voltage2,resistor_value)

                # Add voltage to moving average queue
                moving_avg_queue.append(voltage2)
                samples_lcd.append(pressure_kg_cm2)
                # samples.append([formatted_timestamp,voltage2])
                corrected_voltage = ((0.9295) * voltage_float) + (0.0093)
                samples.append([current_time,corrected_voltage])

                time.sleep(max(0, sampling_interval - (time.time() - current_time)))
            
            logger.info(f"Time {start_time - time.time()} ")

            # Save batch to CSV
            ist_timestamp = datetime.now(ist_tz).strftime('%Y-%m-%d_%H-%M-%S')
            batch_file = os.path.join(output_folder, f"BFA1_Batch{batch_number}_{ist_timestamp}.csv")

            with open(batch_file, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Timestamp","Voltage"])
                writer.writerows(samples)
            logger.info(f"Batch {batch_number} saved: {batch_file}")

            # Update .env with Device ID
            match = re.search(r"BFA\d+", os.path.basename(batch_file))
            if match:
                device_name = match.group(0)
                env_file_path = '/home/bfa/leak_detection_system/.env'
                set_key(env_file_path, 'DEVICE_ID', device_name)
                logger.info(f"Updated DEVICE_ID in .env file to {device_name}")

            # Publish event to queue
            event_message = {
                "file_path": batch_file,
                "event_type": os.getenv('ADC_BATCH_CREATED_EVENT'),
            }
            manager.file_events().put(json.dumps(event_message))
            logger.info(f"Event published to queue for batch {batch_number}.")

            batch_number += 1

        except Exception as e:
            logger.error(f"An error occurred during data collection: {e}", exc_info=True)
            time.sleep(5)  # Retry after a delay

except Exception as e:
    logger.error(f"Initialization failed: {e}")
