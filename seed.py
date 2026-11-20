"""Datos FICTICIOS de demostración. No corresponden a centros ni eventos reales de EAFIT."""
import random
from datetime import timedelta

FMT = "%Y-%m-%d %H:%M:%S"

CENTROS = [
    ("CT-B19-P1", "Centro de cableado Bloque 19 - Piso 1", "Bloque 19 (ficticio)", 15),
    ("CT-B19-P3", "Centro de cableado Bloque 19 - Piso 3", "Bloque 19 (ficticio)", 15),
    ("CT-B33-P2", "Centro de cableado Bloque 33 - Piso 2", "Bloque 33 (ficticio)", 15),
    ("CT-B38-P1", "Centro de cableado Bloque 38 - Piso 1", "Bloque 38 (ficticio)", 30),
    ("CT-BIB-S1", "Centro de cableado Biblioteca - Sótano", "Biblioteca (ficticio)", 30),
    ("CT-B26-P4", "Centro de cableado Bloque 26 - Piso 4", "Bloque 26 (ficticio)", 15),
    ("CT-B14-P2", "Centro de cableado Bloque 14 - Piso 2", "Bloque 14 (ficticio)", None),
    ("CT-LAB-P1", "Centro de cableado Laboratorios - Piso 1", "Laboratorios (ficticio)", 15),
]


def cargar_demo(db, ahora):
    rnd = random.Random(2026)
    ids = {}
    for codigo, nombre, ubic, freq in CENTROS:
        cur = db.execute("INSERT INTO centros(codigo, nombre, ubicacion, frecuencia_reporte_min, creado_en) "
                         "VALUES (?,?,?,?,?)", (codigo, nombre, ubic, freq, (ahora - timedelta(days=30)).strftime(FMT)))
        ids[codigo] = cur.lastrowid

    def ev(cod, tipo, t, nota=""):
        db.execute("INSERT OR IGNORE INTO eventos(centro_id, tipo, ocurrido_en, recibido_en, origen, nota) "
                   "VALUES (?,?,?,?, 'simulado', ?)",
                   (ids[cod], tipo, t.strftime(FMT), (t + timedelta(seconds=2)).strftime(FMT), nota))

    # Historia de 14 días: cortes LOW->HIGH de duración variable y reportes EN_LINEA
    for cod, *_ in CENTROS:
        t = ahora - timedelta(days=14)
        cortes = {"CT-B33-P2": 5, "CT-B38-P1": 3, "CT-B19-P3": 2}.get(cod, rnd.randint(0, 1))
        for _ in range(cortes):
            ini = ahora - timedelta(days=rnd.uniform(0.5, 13.5), minutes=rnd.randint(0, 600))
            ev(cod, "LOW", ini)
            ev(cod, "HIGH", ini + timedelta(minutes=rnd.choice([1, 2, 4, 7, 12, 25])))
            if rnd.random() < 0.4:
                ev(cod, "ENERGIA_RESTABLECIDA", ini + timedelta(minutes=1))
        while t < ahora - timedelta(hours=2):
            ev(cod, "EN_LINEA", t)
            t += timedelta(hours=6)

    # Estados actuales para la demostración
    for cod in ("CT-B19-P1", "CT-B19-P3", "CT-B26-P4", "CT-LAB-P1", "CT-BIB-S1", "CT-B38-P1"):
        ev(cod, "EN_LINEA", ahora - timedelta(minutes=3))
    ev("CT-B33-P2", "LOW", ahora - timedelta(minutes=14), "Corte en curso (demo)")
    ev("CT-B38-P1", "LOW", ahora - timedelta(minutes=4), "Corte breve en curso (demo)")
    ev("CT-B26-P4", "LOW", ahora - timedelta(hours=1, minutes=10))
    ev("CT-B26-P4", "HIGH", ahora - timedelta(hours=1, minutes=2))
    # CT-B14-P2: frecuencia no configurada; CT-B19-P3 deja de reportar
    db.execute("DELETE FROM eventos WHERE centro_id=? AND ocurrido_en > ?",
               (ids["CT-B19-P3"], (ahora - timedelta(hours=3)).strftime(FMT)))
