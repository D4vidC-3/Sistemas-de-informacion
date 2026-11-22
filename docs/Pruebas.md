# Pruebas y correcciones del piloto

El 20/11/2026 se ejecutaron 22 pruebas automatizadas en un ambiente local aislado con Flask 3.1.3. Resultado: 22 aprobadas. La versión pública de referencia anterior tenía 15 pruebas, también ejecutadas y aprobadas durante la revisión. No se ejecutó esta batería contra la base del servidor público.

```bash
python -m unittest discover -s tests -v
```

| Grupo | Pruebas | Cobertura |
|---|---:|---|
| Seguridad | 5 | Login, rechazo de credenciales, CSRF, permisos y clave API |
| Historias | 9 | Centros, eventos, API, estados, historial, criticidad, verificaciones y casos |
| Lógica y regresiones | 8 | Episodios, LOW repetidos, recuperación, ventana, orden de ocurrencia, entrada API, vínculo evento-centro y parámetros positivos |

## Correcciones comprobadas

1. Dos LOW a las 11:40 y 11:59, sin HIGH, consultados a las 12:00: antes se mostraba 1 minuto y dos LOW para recurrencia; ahora 20 minutos y un episodio. La criticidad por duración pasa de Baja a Alta con los umbrales por defecto.
2. Un HIGH seguido de un nuevo LOW abre un segundo episodio. Los reportes repetidos del segundo no abren un tercero.
3. Un corte iniciado diez días antes conserva 14400 minutos de duración aunque un LOW se repita dentro de la ventana de siete días; no suma un inicio nuevo en ella.
4. Los eventos insertados fuera de orden se agrupan por su fecha de ocurrencia.
5. La API rechaza JSON no estructurado como objeto, fechas de tipo incorrecto y fechas futuras, con respuesta 400.
6. Una verificación no puede referenciar un evento de otro centro ni uno inexistente.
7. La ventana de recurrencia y la cantidad de episodios para criticidad alta deben ser positivas.

## Validación antes de publicar en el servidor

Actualizar el código, ejecutar nuevamente la batería, recargar WSGI y comprobar con datos ficticios: inicio de sesión, eventos repetidos, historial, permisos, verificación y borrador. Guardar fecha, versión, casos y resultado. Las capturas anteriores al cambio conservan valor histórico, pero no acreditan la corrección desplegada.

Pendiente externo: demo de aceptación con el contacto del proyecto. Registrar casos probados, observaciones, correcciones y aprobación o rechazo reales. Una prueba automatizada aprobada no equivale a satisfacción del usuario ni a un beneficio medido en operación.

## Ejecución del 22 de noviembre de 2026

28 pruebas aprobadas, 5,078 segundos, en base temporal con datos ficticios. Incluye las 22 regresiones anteriores y seis escenarios nuevos: umbrales de 4/5/9/10 minutos sin reinicio por LOW repetido; retorno posterior al primer aviso; retorno exactamente en el umbral y silencio sin corte; tendencias filtradas sin duplicar episodios; permisos y filtros inválidos; simulación repetida sin alterar eventos, casos ni auditoría. `tests/test_cierre.py` conserva los casos reproducibles.

Se comprobó la lógica y el HTML devuelto por Flask en local. El 22/11 se repitió la batería en PythonAnywhere: 28 pruebas aprobadas en 32,982 s sobre bases temporales; además pasaron nueve comprobaciones HTTP de la URL pública. No se ha obtenido aceptación final de Edwin. [Registros originales](Despliegue_verificado.md). El video previo de 7:57 documenta la versión anterior y conserva su valor histórico; no demuestra estas dos pantallas nuevas.
