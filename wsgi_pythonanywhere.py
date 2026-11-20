# Plantilla del archivo WSGI para PythonAnywhere.
# Copie este contenido en el archivo WSGI que PythonAnywhere crea (pestaña "Web")
# y reemplace USUARIO por su nombre de usuario de PythonAnywhere.
import os
import sys

PROYECTO = "/home/USUARIO/eafit-sistemas-informacion-grupo1"
if PROYECTO not in sys.path:
    sys.path.insert(0, PROYECTO)

# Variables de entorno (los valores reales viven en el archivo .env del servidor, fuera de Git)
env_path = os.path.join(PROYECTO, ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from app import app as application  # noqa: E402
