# Despliegue y operación

El informe identifica https://david23qr4w5e6r.pythonanywhere.com como ambiente académico con datos ficticios. Se comprobó que sirve la pantalla de ingreso el 20/11/2026. Esto no confirma por sí solo la configuración interna, los permisos del cliente ni la actualización de las correcciones.

## Instalación reproducible

Usar los comandos del README y el repositorio `D4vidC-3/Sistemas-de-informacion`. El directorio del clon es `Sistemas-de-informacion`. Si el servidor existente usa otro directorio, conservar su ubicación y ajustar `PROYECTO` y la ruta de estáticos de manera coherente; no mover ni borrar la base existente para adoptar el nombre de esta plantilla.

El WSGI lee `.env` como pares simples `CLAVE=valor`: sin `export`, comillas envolventes ni comentarios al final del valor. No es un lector completo de archivos dotenv. Mantener `SECRET_KEY` estable, `SESSION_COOKIE_SECURE=1` y la API deshabilitada mientras no haya autorización. Las variables definidas en consola para `init-db` no se trasladan automáticamente al proceso WSGI.

## Actualización sin perder datos

1. El responsable del servidor hace una copia privada de la base y de su configuración; no las sube a GitHub.
2. Incorpora la propuesta de cambios al repositorio del equipo y actualiza el clon del servidor.
3. Ejecuta las 28 pruebas en una base temporal mediante unittest. Las pruebas no deben apuntarse a la base operativa.
4. Revisa que WSGI y estáticos sigan apuntando al directorio existente; no vuelve a sembrar ni elimina datos.
5. Pulsa Reload y comprueba `/salud`, ingreso y los escenarios de regresión con datos ficticios.
6. Registra versión, fecha, responsable y resultados. Si falla, vuelve al código anterior y recarga. La corrección no modifica el esquema de datos.

## Respaldo y continuidad

Para una copia coherente de SQLite usar la API de backup del motor o detener escrituras antes de copiar. Guardar la copia fuera de Git con acceso restringido. La restauración debe ensayarse en una ubicación separada antes de considerarla un procedimiento comprobado. La plantilla no implementa respaldo automático ni monitoreo externo.

El responsable de PythonAnywhere debe revisar vigencia y límites del plan en su cuenta. No se promete disponibilidad continua ni capacidad institucional. El código y el informe no sustituyen permisos de TI, autorización de uso de datos ni el acta de entrega al cliente.

## Handoff del cierre del 22 de noviembre

Lucas creó su cuenta propia y publicó el cierre el 22/11 en https://theansw3r.pythonanywhere.com. Versión instalada y verificada: f3ba6d90024b4df79951b23634d3ef58866adfdd. Se ejecutaron 28 pruebas y nueve comprobaciones HTTP, incluidos ambos roles. El ambiente de David no se modificó. [Evidencias y mantenimiento](Despliegue_verificado.md).

Revisar y sustituir en privado cualquier contraseña o clave que haya quedado expuesta en versiones anteriores. Cambiar variables de inicialización no modifica el hash de usuarios ya existentes. La sustitución de contraseñas debe realizarla el responsable del ambiente y comunicarse al profesor por un canal privado; no ponerlas en Git, el informe, capturas ni el video.
