from flask import Flask, render_template, json
from flask_socketio import SocketIO
from gevent import monkey
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler
import redis
import paho.mqtt.client as mqtt

# Parchea para compatibilidad con gevent
monkey.patch_all()

# Configuración de Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, decode_responses=True)

MAX_LINE_LENGTH = 20  # Máximo de datos almacenados por equipo

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # Permitir CORS para evitar problemas de origen cruzado

# Rutas HTML
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/circle')
def index_circle():
    return render_template('index_circle.html')

@app.route('/smoke')
def index_smoke():
    return render_template('index_smoke.html')

@app.route('/camiones')
def index_camiones():
    return render_template('index_camion.html')

@app.route('/camiones_realtime')
def index_camiones_real_time():
    return render_template('index_realtime.html')

@app.route('/camiones_candelaria')
def index_candelaria():
    return render_template('candelaria.html')

@app.route('/antucoya')
def index_antucoya():
    return render_template('antucoya.html')

@app.route('/get_vehicles')
def get_vehicles():
    vehicles = redis_client.keys('*')
    data = {v: obtener_datos(v) for v in vehicles}
    return json.dumps(data)

# Ajuste en la función de almacenamiento en Redis
def guardar_datos(id_vehiculo, datos):
    """
    Almacena los datos en Redis como una lista.
    Si se excede el tamaño máximo, elimina los más antiguos.
    """
    if redis_client.exists(id_vehiculo) and redis_client.type(id_vehiculo) != 'list':
        redis_client.delete(id_vehiculo)  # Elimina si no es lista

    redis_client.lpush(id_vehiculo, json.dumps(datos))
    redis_client.ltrim(id_vehiculo, 0, MAX_LINE_LENGTH - 1)


# Actualización de la función obtener_datos para asegurar que siempre devuelva el formato correcto
def obtener_datos(id_vehiculo):
    data_list = redis_client.lrange(id_vehiculo, 0, -1)
    return [json.loads(data) for data in data_list] if data_list else []


"""
def on_message(client, userdata, msg):
    try:
        # Extrae el ID completo, incluyendo el prefijo (ej.: 'CAEX-320')
        id_vehiculo = msg.topic.split('/')[-2]
        #print()
        message = msg.payload.decode()
        data = json.loads(message)

        if 'latitude' in data and 'longitude' in data:
            # Identifica el tipo a partir del prefijo del ID
            vehicle_type = id_vehiculo.split('-')[0]  # Ej.: 'CAEX' o 'REG'

            # Almacena los datos en Redis usando el ID completo
            guardar_datos(id_vehiculo, {
                'longitude': round(data['longitude'], 5),
                'latitude': round(data['latitude'], 5),
                'altitude_m': data.get('altitude_m', 0.0),
                'speed_kmh': data.get('speed_kmh', 0.0),
                'course': data.get('course', 0.0),
                'pm100': data.get('pm100', 0.0)
            })

            # Recupera la lista completa para ese ID
            vehicle_data_list = obtener_datos(id_vehiculo)

            # Emitir los datos al cliente, incluyendo tipo e ID
            socketio.emit('update_czml', {
                'id': id_vehiculo,
                'type': vehicle_type,
                'datos': vehicle_data_list
            })

    except Exception as e:
        print(f"[Error] Problema al procesar el mensaje: {e}")
"""
def on_message(client, userdata, msg):
    try:
        # Extrae el ID completo, incluyendo el prefijo (ej.: 'CAEX-320')
        id_vehiculo = msg.topic.split('/')[-2]

        #print(id_vehiculo)
        
        # Decodificar el mensaje recibido
        message = msg.payload.decode()
        data = json.loads(message)

        # Validar que 'measurement' y 'equipo' están presentes
        if 'measurement' in data and 'equipo' in data:
            measurement = data['measurement']
            equipo = data['equipo']
            timestamp = data.get('time', 0)

            # Identificar el tipo de vehículo a partir del prefijo del ID
            vehicle_type = id_vehiculo.split('-')[0]  # Ej.: 'CAEX' o 'REG'

            # Redondear los valores de latitud y longitud
            latitude = round(measurement.get('latitude', 0.0), 5)
            longitude = round(measurement.get('longitude', 0.0), 5)
            speed_kmh = measurement.get('speed_kmh', 0.0)

            # Guardar los datos en Redis usando el ID completo
            guardar_datos(id_vehiculo, {
                'longitude': longitude,
                'latitude': latitude,
                'speed_kmh': speed_kmh,
                'altitude_m': -1,
                'course': -1,
                'pm100': -1
            })

            # Recuperar la lista completa de datos para este ID
            vehicle_data_list = obtener_datos(id_vehiculo)

            # Emitir los datos al cliente mediante WebSocket
            socketio.emit('update_czml', {
                'id': id_vehiculo,
                'type': vehicle_type,
                'datos': vehicle_data_list
            })
            #print(f"[INFO] Datos emitidos para {id_vehiculo}: {vehicle_data_list}")

        else:
            print(f"[Advertencia] Mensaje no tiene 'measurement' o 'equipo': {data}")

    except json.JSONDecodeError:
        print(f"[Error] Error al decodificar el mensaje JSON: {msg.payload}")
    except Exception as e:
        print(f"[Error] Problema al procesar el mensaje: {e}")













# Inicializa MQTT
def iniciar_mqtt():
    client = mqtt.Client()
    client.username_pw_set("admin", "Mining2015")
    client.on_message = on_message
    client.connect("desarrollo.mine-360.com", 1883, 60)
    client.subscribe("Antucoya/dataloggers/mapa/#")
    client.loop_start()
    print("[MQTT] Conectado al broker y suscrito al tópico.")

if __name__ == '__main__':
    iniciar_mqtt()

    # Usa gevent con WebSocketHandler
    http_server = WSGIServer(('0.0.0.0', 5050), app, handler_class=WebSocketHandler)
    http_server.serve_forever()

#redis-cli flushall
#sudo systemctl restart app
#sudo systemctl restart get_mmr_eye3.service
