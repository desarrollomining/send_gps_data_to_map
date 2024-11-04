import re
from datetime import datetime
import time
import json
import paho.mqtt.client as mqtt

# Función para convertir latitud/longitud a formato decimal
def convert_to_decimal(degrees, direction, is_longitude=False):
    if is_longitude:
        degrees = float(degrees[:3]) + float(degrees[3:]) / 60
    else:
        degrees = float(degrees[:2]) + float(degrees[2:]) / 60

    if direction in ['S', 'W']:
        degrees *= -1
    return degrees

# Función para convertir nudos a km/h
def knots_to_kmh(knots):
    return float(knots) * 1.852

# Procesar la última línea del archivo
file_path = '/NMEA_GPGGA.txt'  # Cambia esto por la ruta correcta
topic_file_path = 'topic.json'  # Ruta al archivo topic.json

# Función para leer el tópico desde el archivo JSON
def read_topic_from_file(topic_file_path):
    with open(topic_file_path, 'r') as topic_file:
        topic_data = json.load(topic_file)
        return topic_data['topic']  # Asegúrate de que el archivo tiene una clave 'topic'

# Configuración de MQTT
MQTT_BROKER = "desarrollo.mine-360.com"
MQTT_PORT = 1883
MQTT_USER = "admin"
MQTT_PASSWORD = "Mining2015"

# Crear cliente MQTT
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()  # Iniciar el bucle de procesamiento MQTT

    topic = read_topic_from_file(topic_file_path)  # Leer el tópico desde el archivo

    def read_last_line(file_path):
        with open(file_path, 'rb') as file:
            file.seek(0, 2)  # Moverse al final del archivo
            while True:
                position = file.tell()  # Guardar la posición actual
                line = file.readline()  # Leer la última línea
                if not line and position > 0:  # Si no hay nueva línea
                    file.seek(position - 2)  # Moverse hacia atrás en 2 bytes
                    while file.read(1) != b'\n':  # Buscar la última nueva línea
                        file.seek(-2, 1)  # Moverse hacia atrás en 2 bytes
                    line = file.readline()  # Leer la línea encontrada

                yield line.decode().strip()  # Devolver la línea decodificada

    # Bucle para leer la última línea constantemente
    for line in read_last_line(file_path):
        # Extraer fecha y trama de cada línea
        match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\$GPRMC|\$GPGGA),(.+)", line)
        if match:
            date_str = match.group(1)
            nmea_type = match.group(2)
            nmea_data = match.group(3).split(',')

            # Eliminar parte decimal del tiempo
            time_str = nmea_data[0].split('.')[0]

            # Convertir la fecha a un objeto datetime
            date_time_str = f"{date_str.split()[0]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
            try:
                # Convertir la fecha a timestamp
                date_time_obj = datetime.strptime(date_time_str, '%Y-%m-%d %H:%M:%S')
                timestamp_ms = int(date_time_obj.timestamp() * 1000)  # Convertir a milisegundos
            except Exception as e:
                print(f"Error al convertir la fecha y hora: {e}")
                continue

            # Procesar tramas GPRMC y GPGGA
            if nmea_type == '$GPRMC':
                lat = convert_to_decimal(nmea_data[2], nmea_data[3])
                lon = convert_to_decimal(nmea_data[4], nmea_data[5], is_longitude=True)
                speed_knots = nmea_data[6]
                speed_kmh = knots_to_kmh(speed_knots)  # Convertir a km/h
                course = nmea_data[7]
                date = nmea_data[9]
                message = f"Fecha: {date_str}, Timestamp: {timestamp_ms}, Latitud: {lat}, Longitud: {lon}, Velocidad: {speed_knots} nudos ({speed_kmh:.2f} km/h), Curso: {course} grados, Fecha: {date}"
                print(message)

                # Publicar en MQTT
                mqtt_client.publish(topic, message)

            elif nmea_type == '$GPGGA':
                lat = convert_to_decimal(nmea_data[1], nmea_data[2])
                lon = convert_to_decimal(nmea_data[3], nmea_data[4], is_longitude=True)
                quality = nmea_data[5]
                num_sats = nmea_data[6]
                altitude = nmea_data[8]
                message = f"Fecha: {date_str}, Timestamp: {timestamp_ms}, Latitud: {lat}, Longitud: {lon}, Calidad GPS: {quality}, Número de satélites: {num_sats}, Altitud: {altitude}m"
                print(message)

                # Publicar en MQTT
                mqtt_client.publish(topic, message)
        
        time.sleep(1)  # Esperar un segundo antes de leer la próxima línea

except FileNotFoundError:
    print(f"El archivo {file_path} no se encontró.")
except KeyboardInterrupt:
    print("Lectura interrumpida.")
except Exception as e:
    print(f"Ocurrió un error: {e}")
finally:
    mqtt_client.loop_stop()  # Detener el bucle de procesamiento MQTT
    mqtt_client.disconnect()  # Desconectar del broker MQTT
