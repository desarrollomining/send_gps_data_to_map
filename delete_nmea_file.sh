#!/bin/bash

# Ruta del archivo a eliminar
file_path="/NMEA_GPGGA.txt"  # Cambia esta ruta según corresponda

# Verificar si el archivo existe y eliminarlo
if [ -f "$file_path" ]; then
    rm "$file_path"
    echo "El archivo $file_path ha sido eliminado."
else
    echo "El archivo $file_path no existe."
fi
