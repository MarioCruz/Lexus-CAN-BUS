import can
import time
import struct
import requests
from datetime import datetime, timedelta


def get_current_temperature(zip_code):
    try:
        api_key = 'GetKey'
        url = f'http://api.openweathermap.org/data/2.5/weather?zip={zip_code}&appid={api_key}&units=imperial'
        
        response = requests.get(url)
        print(response.text)
        
        if response.status_code == 200:
            data = response.json()
            if 'main' in data:
                temperature = data['main']['temp']
                return temperature
            else:
                print("Temperature data not available")
        else:
            print("Failed to fetch data")
    except Exception as e:
        print("Error getting temperature")

#map number to temperature gauge
def map_number_to_tempGauge(current_temp, low_temp, high_temp):
    if current_temp < low_temp:
        current_temp = low_temp
    elif current_temp > high_temp:
        current_temp = high_temp

    # Calculate the percentage position of the number within the range
    percentage = (current_temp - low_temp) / (high_temp - low_temp)

    # Map the percentage to the output scale segments
    ## gauge goes 90=C, 255=H, everything 165-240=exact midpoint of gauge.  Eliminating the deadpoint, 90 to 165 is the first half of the gauge, 215 to 255 is the upper half.
    if percentage <= 0.5:
        mapped_value = percentage*2 * (150 - 90) + 90
    else:
        mapped_value = (percentage - 0.5)*2 * (255 - 215) + 215

    return mapped_value


def send_temperature(current_temp):
    #convert current temp to gauge scale
    #low temp on gauge=55, hot temp=95
    adjustedTemperature = int(map_number_to_tempGauge(current_temp, 55, 100))
    print('Temperature position on gauge: ' + str(adjustedTemperature))

    # Convert the fuel level to hexadecimal
    hex_temperature = hex(adjustedTemperature)[2:].zfill(2)
    temperature_byte = int(hex_temperature, 16)
    # print(temperature_byte)
 
    # Create a CAN message
    ##having 0x46 or 0x43 in position 1 turns off steering and tpms lights
    msg_temperature = can.Message(
        arbitration_id=0x3B4,
        data=[0x46, 0x00, temperature_byte, 0x00, 0x00, 0x00, 0x00, 0x00],
        is_extended_id=False
    )
  
    return msg_temperature


def get_next_high_tide():
    # NOAA API endpoint for tide predictions
    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

    # Determine current time and time 18 hours from now
    current_time = datetime.now()
    end_time = current_time + timedelta(hours=18)

    # Formatting start and end times for API request
    start_date = current_time.strftime('%Y%m%d %H:%M')
    end_date = end_time.strftime('%Y%m%d %H:%M')

    # Parameters for the API request
    params = {
        "begin_date": start_date,
        "end_date": end_date,
        "station": "8723214",  # Miami, Florida station ID
        "product": "predictions",
        "datum": "MLLW",
        "interval": "hilo",
        "units": "english",
        "time_zone": "lst",
        "format": "json",
    }

    # Sending the API request
    response = requests.get(url, params=params)

    # Checking if the request was successful
    if response.status_code == 200:
        # Accessing the tide predictions data
        data = response.json()

        # Checking if predictions are present in the response
        if "predictions" in data:
            predictions = data["predictions"]

            # Filtering high tides
            high_tides = [tide for tide in predictions if tide['type'] == 'H' and datetime.strptime(tide['t'], '%Y-%m-%d %H:%M') > current_time]

            if high_tides:
                # Find the time of the next high tide
                next_high_tide = min(high_tides, key=lambda x: datetime.strptime(x['t'], '%Y-%m-%d %H:%M'))
                return datetime.strptime(next_high_tide['t'], '%Y-%m-%d %H:%M')
        
    return None

def calculate_tide_percentage(next_high_tide_time):
    if next_high_tide_time:
        # Determine current time
        current_time = datetime.now()
        print('Next high tide: ' + str(next_high_tide_time))

        # Calculate time difference between now and the next high tide
        time_until_high_tide = next_high_tide_time - current_time
        print('Time until high tide: ' + str(time_until_high_tide))
        hours_until_high_tide = time_until_high_tide.total_seconds() / 3600  # Convert to hours

        # Calculate tide percentage based on the specified criteria
        if 0 <= hours_until_high_tide <= 6:
            tide_percentage = (1-(hours_until_high_tide / 6)) * 100
        else:
            adjusted_hours = hours_until_high_tide - 6
            tide_percentage = (adjusted_hours / 6) * 100
        
        print('Tide percentage: ' + str(tide_percentage))

        return tide_percentage

    return None




def send_fuel(fuel_level): #aka tide data

    #round fuel to nearest 25%  ....remove this if I can figure out how to get the cluster to show other positions
    rounded_percent = round(fuel_level / 25) * 25
    
    #map percentage to value expected by cluster
    rounded_values = {0: 4, 25: 8, 50: 16, 75: 32, 100: 64}
    fuel_level = rounded_values.get(rounded_percent, rounded_percent)
    print("Fuel position on gauge: " + str(fuel_level))



    fuel_level = int(fuel_level)
    # Convert the fuel level to hexadecimal
    hex_fuel = hex(fuel_level)[2:].zfill(2)
    #print(hex_fuel)
    fuel_byte = int(hex_fuel, 16)
    #print(fuel_byte)
 
    # Create a CAN message with the ID 0x7C0
    msg_fuel = can.Message(
        arbitration_id=0x7C0,
        data=[0x04, 0x30, 0x03, 0x00, fuel_byte, 0x00, 0x00, 0x00],
        is_extended_id=False
    )

    return msg_fuel
 




 
def send_speed(current_time):
    #convert time to mph speed - keep in mind minutes are now a percentage of 100 and not equal to the number of minutes
    speed_mph = (int(time.strftime("%I", current_time)) * 100 + (current_time.tm_min/60*100))/10
    #convert speed to a percentage of the gauge
    speedValue = int(speed_mph * (98/160)) #98/160 is to adjust for the range of the gauge


    # Convert the speed to hexadecimal
    hex_speed = hex(speedValue)[2:].zfill(4)
    speed_bytes = [int(hex_speed[i:i+2], 16) for i in range(0, len(hex_speed), 2)]
 
    # Create a CAN message with the ID 0x0B4 for speed
    msg_speed = can.Message(
        arbitration_id=0x0B4,
        data=[0x00, 0x00, 0x00, 0x00, speed_bytes[0], speed_bytes[1], 0x66, 0xB5],
        is_extended_id=False
    )
    
    print('Speed mph: ' + str(speed_mph))
    print('Speed percent of gauge: '+ str(speedValue))
    return msg_speed
 



def send_rpm(current_time):
    ####note there is an issue with sending decimal data.  Any RPM that does not divide evenly by 200 needs to be rounded until this is fixed
    ####remove seconds from RPM value to have a ticking action when the minute changes -- will only matter once the above is fixed

    # convert time to an RPM
    rpm_value = current_time.tm_min * 100 + current_time.tm_sec
    print('Calculated RPM: ' + str(rpm_value))
    # Ensure the RPM value is within the acceptable range
    rpm_value = max(0, min(8000, rpm_value))  # Considering a maximum of 8000 RPM

    # math to make RPM what gauge expects
    rpm_value = round(rpm_value / 200)
    
    # Convert the RPM value to four bytes in big-endian format (32-bit integer)
    rpm_bytes = rpm_value.to_bytes(4, byteorder='big')
    
    # Create a CAN message with the ID 0x1D0 for RPM
    msg_rpm = can.Message(
        arbitration_id=0x2C4,
        data=[rpm_bytes[3], rpm_bytes[2], rpm_bytes[1], rpm_bytes[0], 0x00, 0x00, 0x00, 0x00],
        is_extended_id=False
    )

    print('Gauge RPM: ' + str(rpm_value * 2 * 100))
    return msg_rpm









#turn off warning lights
###turn off abs, yellow brake light and red brake light
msg_brake = can.Message(
        arbitration_id=0x3B7,
        data=[ 0xa9, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
        is_extended_id=False
    )











# Connect to the CAN bus
bus = can.interface.Bus(channel='can0', bustype='socketcan')
 



#initalize variables
latest_tideFetchAttempted_time = None
latest_temperatureFetchAttempted_time = None
current_temperature_true_time = None



while True:
    print('------------------------------')
    print('------------------------------')
    print('------------------------------')
    # Get the current time
    current_time = time.localtime()
    print(time.strftime("%Y-%m-%d %H:%M:%S", current_time))
    

    #update temperature if more than 30 minutes have passed
    print('--')
    if (latest_temperatureFetchAttempted_time is None) or (time.time() - latest_temperatureFetchAttempted_time >= 30*60): #30 minutes * 60seconds
        try:
            latest_temperatureFetchAttempted_time = time.time()
            current_temperature = get_current_temperature('33129')
            current_temperature_true_time = time.time()
        except:
            print('Error getting temperature')
    print("Current temperature: " + str(current_temperature))
    print('Temperature true age: ' + str(time.time() - current_temperature_true_time))
    print("Temperature callout attempted age: "+ str(time.time() - latest_temperatureFetchAttempted_time))    
        
    
    
    #get next high tide if current time is later than next high tide
    #calculate tide percentage
    print('--')
    if (latest_tideFetchAttempted_time is None) or (datetime.now() >= nextHighTide):
        if (latest_tideFetchAttempted_time is None) or (time.time() - latest_tideFetchAttempted_time >= 15*60): #15 minutes * 60seconds have passed since last attempt at getting tide info
                print("getting tide")
                latest_tideFetchAttempted_time=time.time()
                try:
                    nextHighTide = get_next_high_tide()
                except:
                    print('Error getting tide')
    tidePercent = calculate_tide_percentage(nextHighTide)
    print("Tide callout attempted age: "+ str(time.time() - latest_tideFetchAttempted_time))
    
    

    #send data to canbus
    print('----data sent to canbus----')
    # Send hour value as MPH and minute value as RPM
    bus.send(send_speed(current_time))
    bus.send(send_rpm(current_time))
    #send temperature as coolant temp and tide as gas level
    bus.send(send_temperature(current_temperature))
    bus.send(send_fuel(tidePercent))

    #turn off remaining warning lights
    bus.send(msg_brake)


    # Wait a short while before updating the time
    #needles don't wobble if sleep <=0.1...  setting a little lower to be safe
    time.sleep(0.07)
