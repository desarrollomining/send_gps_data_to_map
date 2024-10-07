import requests
import json
import os
import subprocess


def get_machine_id():
    result = subprocess.run(['machineid'], stdout=subprocess.PIPE)
    machineid = result.stdout.decode('utf-8').strip()
    return machineid

def get_datalogger_data(machine_id):
    url = f"http://core.mine-360.com:5000/datalogger?machineid={machine_id}"
    
    try:
        # Hacer la solicitud GET a la API
        response = requests.get(url)
        response.raise_for_status()  # Levantar excepción si hay error en la respuesta

        # Convertir la respuesta JSON
        data = response.json()

        # Especificar el nombre del archivo donde se guardará el JSON
        file_name = f"topic.json"

        # Obtener la ruta actual donde se ejecuta el script
        current_directory = os.getcwd()

        # Guardar el archivo JSON en la carpeta actual
        file_path = os.path.join(current_directory, file_name)
        with open(file_path, 'w') as json_file:
            json.dump(data, json_file, indent=4)
        
        print(f"Datos guardados correctamente en {file_path}")

    except requests.exceptions.RequestException as e:
        print(f"Error al obtener los datos: {e}")

if __name__ == "__main__":
    # Obtener el machine-id automáticamente
    machine_id = get_machine_id()

    if machine_id:
        get_datalogger_data(machine_id)
    else:
        print("No se pudo obtener el machine-id.")
