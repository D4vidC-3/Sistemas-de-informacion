# Backlog y trazabilidad funcional

## Alcance comprobable

| HU | Como usuario quiero | Para | Criterios verificables | Código y prueba | Estado técnico |
|---|---|---|---|---|---|
| HU-01 | Como coordinador quiero registrar centros; como técnico, consultarlos | Identificar el origen de un reporte | Código único, nombre, búsqueda y detalle; alta restringida al coordinador | rutas centros; test_hu01 y permisos | Implementada |
| HU-02 | Como técnico quiero registrar eventos persistentes | Conservar tipo, fecha, origen y centro | Formulario y API con clave; duplicado idéntico no crea fila; fecha futura rechazada | registrar_evento; test_hu02; test_api_rechaza_json_invalido_y_fechas_futuras | Implementada |
| HU-03 | Como técnico quiero separar electricidad y comunicación | Evitar inferir un corte desde el silencio | Estado eléctrico por LOW/HIGH; comunicación por frecuencia; un LOW repetido mantiene inicio del corte | estado_centro; test_hu03; test_low_repetidos_conservan_inicio_y_un_solo_episodio | Implementada con corrección local pendiente de despliegue |
| HU-04 | Como técnico quiero filtrar y exportar el historial | Revisar la secuencia por centro | Filtros, CSV y episodios ordenados por ocurrencia; HIGH aislado no crea episodio | historial y episodios; test_hu04; test_episodios; test_eventos_desordenados_se_agrupan_por_ocurrencia | Implementada |
| HU-05 | Como coordinador quiero configurar la criticidad | Orientar una revisión humana uniforme | Cuatro niveles, umbrales ordenados, ventana y recurrencia positivas; técnico sin permiso de edición | clasificar y criticidad; test_hu05; test_reglas_rechazan_ventana_o_recurrencia_no_positivas | Implementada con corrección local pendiente de despliegue |
| HU-09 | Como técnico quiero registrar y cerrar verificaciones | Conservar diagnóstico, responsable y resultado | Alcance y área válidos; evento del mismo centro; cierre exige resultado | verificaciones; test_hu09; test_verificacion_rechaza_evento_de_otro_centro | Implementada |
| HU-06-SIM | Como técnico quiero preparar un borrador confirmado | Dejar evidencia de la decisión humana | Confirmación, motivo y prioridad; solo coordinador registra referencia o descarta; sin envío a Aranda | casos; test_hu06 | Implementada |
| HU-10 | Como coordinador quiero tendencias por centro y periodo | Analizar recurrencia | Gráficas por periodo y distinción señal/episodio | /tendencias; test_tendencias_periodo_centro_y_episodios_sin_duplicar | Implementada y probada localmente el 22/11; despliegue pendiente |
| HU-08-SIM | Como técnico quiero ensayar avisos de 5 y 10 minutos | Validar escalamiento antes de notificar | Avisos de prueba y cancelación por retorno | /avisos-simulados; test_avisos_umbral_y_low_repetido; pruebas de retorno y permisos | Implementada y probada localmente el 22/11; despliegue pendiente |
| HU-06-REAL | Como personal autorizado quiero integrar Aranda | Evitar doble registro | Contrato API, identidad, permisos y validación institucional | Sin integración | Fuera del alcance |
| HU-07 | Como personal autorizado quiero ingesta de ESP32 | Recibir señales reales | Autorización, autenticación de origen y piloto controlado | Existe API genérica; no se probaron dispositivos reales | Fuera del alcance |
| HU-08-REAL | Como técnico quiero notificaciones operativas | Avisar por un canal aprobado | Canal, destinatarios, reglas y permiso institucional | Sin integración | Fuera del alcance |
| HU-11 | Como TI quiero un despliegue institucional | Operar con soporte y controles institucionales | Identidad, respaldo, capacidad, monitoreo y aprobación | Solo piloto académico | Fuera del alcance |

Implementada describe código y pruebas, no aceptación del cliente. Las estimaciones de 3 y 5 puntos del informe deben identificarse como retrospectivas mientras no exista el plan original. No se derivan velocidades históricas de esos valores.

## Continuidad de procesos y diagnóstico

P01, P02 y P03 se usan con el significado del informe de Entrega 2: monitoreo, verificación y diagnóstico, y gestión de incidencias. P02 del portafolio de automatización de Edwin significa generación de reportes; no es el mismo proceso.

La lectura directa de los dos libros de diagnóstico utilizados en el proyecto conserva D09 para tiempos de ciclo y D12 para calidad de datos. El libro completado por Edwin puntúa ambos con 2/5 y señala falta de evidencia específica. D13 corresponde a analítica para decisiones y tiene 5/5 frente a objetivo 4; no se presenta como una brecha positiva. D07 estandarización y D08 automatización tienen 3/5 frente a 4; D22 control de acceso, 3/5 frente a 4. Son indicadores del diagnóstico, no defectos institucionales comprobados por la aplicación.

| Necesidad y proceso | TO BE | HU | Componente | Evidencia de prueba |
|---|---|---|---|---|
| D12 calidad del dato / P01 | Identificar centro y conservar evento sin duplicado idéntico | 01, 02 | centros y eventos | test_hu01, test_hu02 |
| D07 estandarización / P01 | Separar señales, silencio y episodios | 03 | estado_centro | test_hu03 y regresiones de LOW repetidos |
| D12 calidad del dato; afinidad D13 sin brecha positiva / P01–P02 | Consultar y agrupar historial | 04 | historial y episodios | test_hu04 y test_episodios |
| D07 estandarización / P02 | Priorizar revisión con regla visible | 05 | reglas y clasificar | test_hu05 y validación de parámetros |
| D09 medición / P02 | Registrar verificación y resultado | 09 | verificaciones y auditoria | test_hu09; no demuestra reducción del tiempo |
| D08 automatización / P03 | Preparar borrador y referencia humana | 06-SIM | casos | test_hu06 |
| D22 acceso / transversal | Restringir acciones por rol | Seguridad | login y decoradores | TestSeguridad |

## Gestión de sprints

El Sprint 1 reportado abarca 16–22/10/2026, siete días, y corresponde al mockup. El informe reporta un segundo periodo 23/10–20/11/2026. El registro retrospectivo del alcance de ese periodo no demuestra planificación ni seguimiento diario. Las actualizaciones en Azure deben conservar sus fechas reales de creación y cambio; no reconstruir burndown, horas o cierres inexistentes.

La revisión de cierre debe guardar tablero actual, detalle de dos HU, cambios y causas de pendientes; la retrospectiva debe confirmarse con el equipo. Las pruebas del código y la aceptación de la empresa son etapas diferentes de la definición de terminado.

La revisión técnica del 22/11 completa las dos historias simuladas. No constituye una ceremonia de retrospectiva celebrada por el equipo ni aceptación de Edwin. No modifica los registros históricos del sprint.
