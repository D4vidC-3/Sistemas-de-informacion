-- Esquema de la base de datos (SQLite). Datos ficticios / de prueba.
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('coordinador', 'tecnico')),
    password_hash TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS centros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    ubicacion TEXT,
    frecuencia_reporte_min INTEGER,          -- frecuencia esperada de reporte; NULL = no configurada
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    centro_id INTEGER NOT NULL REFERENCES centros(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('LOW', 'HIGH', 'EN_LINEA', 'ENERGIA_RESTABLECIDA')),
    ocurrido_en TEXT NOT NULL,               -- cuándo ocurrió (hora Bogotá)
    recibido_en TEXT NOT NULL,               -- cuándo se registró en el sistema
    origen TEXT NOT NULL CHECK (origen IN ('manual', 'simulado', 'api')),
    nota TEXT,
    registrado_por INTEGER REFERENCES usuarios(id),
    UNIQUE (centro_id, tipo, ocurrido_en)    -- evita duplicados idénticos
);
CREATE INDEX IF NOT EXISTS ix_eventos_centro_fecha ON eventos(centro_id, ocurrido_en);

CREATE TABLE IF NOT EXISTS reglas (
    clave TEXT PRIMARY KEY,
    valor INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS verificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    centro_id INTEGER NOT NULL REFERENCES centros(id),
    evento_id INTEGER REFERENCES eventos(id),
    autor_id INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en TEXT NOT NULL,
    diagnostico TEXT NOT NULL,
    alcance TEXT NOT NULL CHECK (alcance IN ('sectorizado', 'general', 'incierto')),
    area_responsable TEXT NOT NULL CHECK (area_responsable IN ('redes', 'campus', 'mesa')),
    estado TEXT NOT NULL CHECK (estado IN ('Abierta', 'En curso', 'Cerrada')),
    resultado TEXT,
    cerrado_en TEXT,
    cerrado_por INTEGER REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS casos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verificacion_id INTEGER NOT NULL REFERENCES verificaciones(id),
    motivo TEXT NOT NULL,
    prioridad TEXT NOT NULL,
    creado_por INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en TEXT NOT NULL,
    estado TEXT NOT NULL,                    -- Borrador | Registrado en Aranda (manual) | Descartado
    referencia_aranda TEXT,
    actualizado_en TEXT
);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER REFERENCES usuarios(id),
    accion TEXT NOT NULL,
    entidad TEXT NOT NULL,
    entidad_id INTEGER,
    detalle TEXT,
    fecha TEXT NOT NULL
);
