# Centro de Operaciones de Redes · EAFIT (Grupo 1)

Solución de la **Entrega 3** del curso *Sistemas de Información* (Universidad EAFIT, 2026-2).

Es una aplicación web para el área de **Infraestructura y Operaciones de Redes**. Permite registrar y consultar los eventos de alimentación EPM de los centros de cableado, y separa el **estado eléctrico** (señales LOW/HIGH) del **estado de comunicación** (reportes según la frecuencia configurada). También clasifica la criticidad, registra la **verificación humana** y prepara **borradores de caso** para Aranda, sin integración automática.

> Todos los datos son **ficticios o de prueba**. No hay conexión con dispositivos ESP32 reales, con Aranda ni con canales de notificación institucionales.

## Accesos y documentación

- Aplicación indicada en el informe: https://david23qr4w5e6r.pythonanywhere.com
- Azure DevOps: https://dev.azure.com/llsaldarrq/EAFIT-Sistemas-Informacion
- Documentación para la Wiki: [Inicio](docs/Home.md).

Las credenciales de prueba se comparten por canal privado. La URL corresponde al despliegue documentado por el equipo; cada actualización requiere ejecutar las pruebas y recargar el servidor.

## Funcionalidades (historias de usuario)

| HU | Funcionalidad | Ruta |
|---|---|---|
| HU-01 | Registrar y consultar centros de cableado (búsqueda y detalle) | `/centros` |
| HU-02 | Registrar eventos persistentes (manual, simulado o por API) sin duplicados | `/eventos`, `POST /api/eventos` |
| HU-03 | Estado eléctrico y estado de comunicación por separado | `/` |
| HU-04 | Historial individual y consolidado con filtros y exportación CSV | `/historial` |
| HU-05 | Reglas de criticidad configurables (Baja, Media, Alta, Crítica) | `/criticidad` |
| HU-10 | Tendencias por centro y periodo, señales y episodios diferenciados | `/tendencias` (coordinador) |
| HU-08-SIM | Temporizadores simulados de 5/10 minutos y cancelación por HIGH | `/avisos-simulados` |
| HU-09 | Verificación humana: diagnóstico, alcance, área y cierre con resultado obligatorio | `/verificaciones` |
| HU-06-SIM | Borrador de caso con confirmación humana; registro manual de la referencia de Aranda | `/casos` |

Funciones adicionales: login con roles (`coordinador` y `tecnico`), protección CSRF, contraseñas con hash, auditoría de acciones (`/auditoria`), episodios LOW→HIGH por centro y endpoint de salud (`/salud`).

## Tecnologías

- Python 3.10+ y Flask 3
- SQLite (módulo estándar `sqlite3`)
- HTML + CSS con plantillas Jinja2, sin dependencias de front-end
- Pruebas con `unittest` y el cliente de pruebas de Flask

## Estructura

```
app.py                  Aplicación Flask (rutas, reglas de negocio, seguridad)
schema.sql              Modelo de datos
seed.py                 Datos ficticios de demostración
templates/              Vistas HTML (Jinja2)
static/style.css        Estilos
tests/test_app.py       Pruebas funcionales por historia de usuario
wsgi_pythonanywhere.py  Plantilla de despliegue en PythonAnywhere
```

## Instalar y ejecutar en local

```bash
git clone https://github.com/D4vidC-3/Sistemas-de-informacion.git
cd Sistemas-de-informacion
python -m venv .venv
# Windows: .venv\Scripts\activate    |   Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Contraseñas de los usuarios iniciales (si no se definen, se generan y se muestran en pantalla)
# Windows PowerShell:  $env:COORD_PASSWORD="..."; $env:TECNICO_PASSWORD="..."
# Mac/Linux:           export COORD_PASSWORD=... TECNICO_PASSWORD=...
flask --app app init-db          # crea la base, los usuarios y los datos ficticios
flask --app app run              # abre http://127.0.0.1:5000
```

Usuarios creados: `coordinador` (puede crear centros, editar reglas y gestionar casos) y `tecnico` (registra eventos y verificaciones).

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas comprueban escenarios de las HU implementadas, permisos por rol, CSRF, API y regresiones de episodios. El resultado y sus límites se registran en `docs/Pruebas.md`; no sustituyen la aceptación de la empresa.

## Configuración y secretos

Las credenciales **no** están en el código. Se configuran con variables de entorno (ver `.env.example`):

| Variable | Uso |
|---|---|
| `SECRET_KEY` | Firma de la sesión |
| `COORD_PASSWORD`, `TECNICO_PASSWORD` | Contraseñas iniciales (solo en `init-db`) |
| `API_KEY` | Habilita `POST /api/eventos` (vacía = API deshabilitada) |
| `DATABASE_PATH` | Ruta del archivo SQLite |
| `SESSION_COOKIE_SECURE` | `1` en producción con HTTPS |

El archivo `.env` y la base de datos están excluidos del repositorio (`.gitignore`).

## API para dispositivos (base para una fase posterior)

```bash
curl -X POST https://<servidor>/api/eventos \
  -H "X-API-Key: <API_KEY>" -H "Content-Type: application/json" \
  -d '{"codigo_centro":"CT-B33-P2","tipo":"LOW","ocurrido_en":"2026-11-20 10:00:00"}'
```

Tipos válidos: `LOW`, `HIGH`, `EN_LINEA`, `ENERGIA_RESTABLECIDA`. Los eventos idénticos (mismo centro, tipo y hora) no se duplican. Conectar ESP32 reales requiere la autorización de TI y Seguridad de EAFIT.

## Despliegue en PythonAnywhere (plan gratuito)

1. Crear una cuenta en pythonanywhere.com y abrir una consola **Bash**.
2. `git clone https://github.com/D4vidC-3/Sistemas-de-informacion.git`
3. `cd Sistemas-de-informacion && pip install --user -r requirements.txt`
4. Crear el archivo `.env` a partir de `.env.example` con valores reales.
5. `set -a; source .env; set +a; flask --app app init-db`
6. En la pestaña **Web**, crear una app con *Manual configuration* (Python 3.10 o superior). En el archivo WSGI, pegar el contenido de `wsgi_pythonanywhere.py`, cambiando `USUARIO`.
7. En *Static files*, agregar la URL `/static/` apuntando a `/home/USUARIO/Sistemas-de-informacion/static`.
8. Activar *Force HTTPS* y pulsar **Reload**. La app queda disponible en `https://USUARIO.pythonanywhere.com`.

Para actualizar: `git pull` en la consola y **Reload** en la pestaña Web.

## Cálculo de episodios y criticidad

El primer LOW abre un episodio y el siguiente HIGH lo cierra. Otro LOW durante el corte conserva su inicio. La duración del corte en curso se mide desde ese primer LOW; la recurrencia cuenta episodios cuyo inicio cae dentro de la ventana configurada, incluido el que siga abierto. Un corte iniciado antes de la ventana conserva su duración, pero no suma un nuevo inicio dentro de ella. La comunicación considera el último reporte recibido, sin deducir normalización eléctrica.

## Alcance y límites

Quedan fuera de esta entrega: la integración real con Aranda (HU-06-REAL), la ingesta desde ESP32 reales (HU-07), las notificaciones operativas (HU-08) y el despliegue institucional (HU-11), porque requieren permisos de TI y Seguridad. La criticidad orienta la revisión, pero no crea tickets: la decisión de abrir, escalar o cerrar un caso es siempre humana.

## Cierre técnico del 22 de noviembre de 2026

Se completaron HU-10 y HU-08-SIM y se ejecutaron 28 pruebas aprobadas en una base temporal local. El simulador reconstruye eventos hasta la hora seleccionada; no envía notificaciones ni registra entregas de mensajes. Las tendencias cuentan inicios de episodios, sin duplicar LOW repetidos. No hay cambios del esquema SQLite.

La publicación de estos cambios en GitHub no actualiza automáticamente PythonAnywhere. El responsable del alojamiento debe seguir [la actualización de operación](docs/Operacion.md). La reunión del 17/11 respalda el mockup, las historias y P01–P03; la aceptación de esta aplicación final no se ha realizado. No se acredita rotación de credenciales del servidor sin acceso a su administración.

[Contribuciones verificables y apoyo de IA](docs/Contribuciones.md). [Pruebas](docs/Pruebas.md). [Manual de las nuevas funciones](docs/Manual.md).

[Demostración práctica Odoo ERP/CRM con capturas y análisis](docs/Demo_ERP_CRM.md).

[Gestión de sprints, cronología sustentada y aportes confirmados](docs/Gestion_sprints.md). Registro retrospectivo del 22/11; conserva las fechas reales de Azure y no reconstruye horas diarias.
