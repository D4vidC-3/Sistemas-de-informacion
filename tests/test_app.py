"""Pruebas funcionales: verifican los criterios de aceptación de las HU.

Ejecutar desde la carpeta del proyecto:  python -m unittest discover -s tests -v
"""
import os
import re
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.gettempdir(), "redes_import.db"))

from werkzeug.security import generate_password_hash  # noqa: E402

import app as appmod  # noqa: E402
from seed import cargar_demo  # noqa: E402


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = appmod.create_app({"DATABASE": os.path.join(self.tmp, "t.db"), "TESTING": True,
                                      "API_KEY": "clave-de-prueba"})
        with self.app.app_context():
            self.app.init_db()
            db = self.app.get_db()
            for u, rol in (("coord", "coordinador"), ("tec", "tecnico")):
                db.execute("INSERT INTO usuarios(usuario, nombre, rol, password_hash) VALUES (?,?,?,?)",
                           (u, u.upper(), rol, generate_password_hash("clave123")))
            cargar_demo(db, appmod.ahora())
            db.commit()
        self.c = self.app.test_client()

    def csrf(self, path="/login"):
        html = self.c.get(path).get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def login(self, usuario="tec"):
        return self.c.post("/login", data={"usuario": usuario, "password": "clave123", "csrf": self.csrf()},
                           follow_redirects=True)

    def db(self):
        return self.app.get_db()


class TestSeguridad(BaseTest):
    def test_requiere_login(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_login_incorrecto(self):
        r = self.c.post("/login", data={"usuario": "tec", "password": "mala", "csrf": self.csrf()})
        self.assertIn("incorrectos", r.get_data(as_text=True))

    def test_post_sin_csrf_rechazado(self):
        self.login()
        r = self.c.post("/eventos", data={"centro_id": 1, "tipo": "LOW"})
        self.assertEqual(r.status_code, 400)

    def test_tecnico_no_edita_reglas_ni_crea_centros(self):
        self.login("tec")
        t = self.csrf("/criticidad")
        r = self.c.post("/criticidad", data={"csrf": t, "accion": "guardar", "umbral_media_min": 1,
                                             "umbral_alta_min": 2, "umbral_critica_min": 3,
                                             "repeticiones_alta": 1, "ventana_dias": 1})
        self.assertEqual(r.status_code, 403)
        r = self.c.post("/centros/nuevo", data={"csrf": t, "codigo": "X", "nombre": "X"})
        self.assertEqual(r.status_code, 403)

    def test_api_requiere_clave(self):
        r = self.c.post("/api/eventos", json={"codigo_centro": "CT-B19-P1", "tipo": "LOW"})
        self.assertEqual(r.status_code, 401)


class TestHistorias(BaseTest):
    def test_hu01_registrar_y_buscar_centro(self):
        self.login("coord")
        t = self.csrf("/centros")
        r = self.c.post("/centros/nuevo", data={"csrf": t, "codigo": "ct-test-01", "nombre": "Centro de prueba",
                                                "ubicacion": "Bloque X", "frecuencia_reporte_min": "15"},
                        follow_redirects=True)
        self.assertIn("CT-TEST-01", r.get_data(as_text=True))
        r = self.c.get("/centros?q=TEST")
        html = r.get_data(as_text=True)
        self.assertIn("CT-TEST-01", html)
        self.assertNotIn("CT-B19-P1", html)

    def test_hu02_evento_persistente_y_sin_duplicados(self):
        self.login()
        t = self.csrf("/eventos")
        data = {"csrf": t, "centro_id": 1, "tipo": "LOW", "ocurrido_en": "2026-11-01T10:00", "origen": "manual"}
        self.c.post("/eventos", data=data)
        r = self.c.post("/eventos", data=data, follow_redirects=True)
        self.assertIn("duplicado", r.get_data(as_text=True))
        with self.app.app_context():
            n = self.db().execute("SELECT COUNT(*) FROM eventos WHERE centro_id=1 AND ocurrido_en='2026-11-01 10:00:00'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_hu02_api_registra_evento(self):
        r = self.c.post("/api/eventos", headers={"X-API-Key": "clave-de-prueba"},
                        json={"codigo_centro": "CT-B19-P1", "tipo": "HIGH", "ocurrido_en": "2026-11-02 08:00:00"})
        self.assertEqual(r.status_code, 201)
        r = self.c.post("/api/eventos", headers={"X-API-Key": "clave-de-prueba"},
                        json={"codigo_centro": "CT-B19-P1", "tipo": "HIGH", "ocurrido_en": "2026-11-02 08:00:00"})
        self.assertTrue(r.get_json()["duplicado"])

    def test_hu03_estados_separados(self):
        self.login()
        html = self.c.get("/").get_data(as_text=True)
        fila_b33 = html[html.index("CT-B33-P2"):][:900]
        self.assertIn("Sin alimentación EPM", fila_b33)
        self.assertIn("Comunicando", fila_b33)
        fila_b193 = html[html.index("CT-B19-P3"):][:900]
        self.assertIn("Sin comunicación", fila_b193)
        self.assertIn("Con alimentación EPM", fila_b193)  # silencio != corte
        fila_b14 = html[html.index("CT-B14-P2"):][:900]
        self.assertIn("Frecuencia no configurada", fila_b14)

    def test_hu04_historial_filtrado(self):
        self.login()
        html = self.c.get("/historial?centro=1&tipo=EN_LINEA").get_data(as_text=True)
        self.assertIn("EN_LINEA", html)
        self.assertNotIn("<td>LOW</td>", html)
        self.assertNotIn("CT-B33-P2</a>", html)
        r = self.c.get("/historial.csv?centro=1")
        self.assertEqual(r.mimetype, "text/csv")

    def test_hu05_clasificacion(self):
        with self.app.app_context():
            self.login()
            # Reglas por defecto: media 5, alta 10, crítica 30, repeticiones 3
            t = self.csrf("/criticidad")
            casos = [(2, 0, "Baja"), (6, 0, "Media"), (12, 0, "Alta"), (2, 3, "Alta"), (31, 0, "Crítica"), (12, 3, "Crítica")]
            for d, r, esperado in casos:
                html = self.c.post("/criticidad", data={"csrf": t, "accion": "probar", "duracion": d,
                                                        "repeticiones": r}).get_data(as_text=True)
                self.assertRegex(html, rf"Resultado: <span class=\"status [a-z]+\">{esperado}</span>", (d, r))

    def test_hu05_coordinador_valida_umbrales(self):
        self.login("coord")
        t = self.csrf("/criticidad")
        r = self.c.post("/criticidad", data={"csrf": t, "accion": "guardar", "umbral_media_min": 20,
                                             "umbral_alta_min": 10, "umbral_critica_min": 30,
                                             "repeticiones_alta": 3, "ventana_dias": 7}, follow_redirects=True)
        self.assertIn("media &lt; alta &lt; crítica", r.get_data(as_text=True))

    def test_hu09_verificacion_y_cierre_con_resultado(self):
        self.login()
        t = self.csrf("/verificaciones/nueva?centro=3")
        r = self.c.post("/verificaciones/nueva", data={"csrf": t, "centro_id": 3, "alcance": "sectorizado",
                                                       "area": "campus", "diagnostico": "Sin energía en el piso 2, se avisa a Campus."},
                        follow_redirects=True)
        self.assertIn("Verificación registrada", r.get_data(as_text=True))
        r = self.c.post("/verificaciones/1", data={"csrf": t, "estado": "Cerrada", "resultado": ""}, follow_redirects=True)
        self.assertIn("Para cerrar debe registrar el resultado", r.get_data(as_text=True))
        r = self.c.post("/verificaciones/1", data={"csrf": t, "estado": "Cerrada",
                                                   "resultado": "Switch y enlaces operando, confirmado con el área."},
                        follow_redirects=True)
        self.assertIn("Cerrada", r.get_data(as_text=True))
        with self.app.app_context():
            v = self.db().execute("SELECT * FROM verificaciones WHERE id=1").fetchone()
            self.assertIsNotNone(v["cerrado_por"])
            n = self.db().execute("SELECT COUNT(*) FROM auditoria WHERE entidad='verificacion'").fetchone()[0]
            self.assertGreaterEqual(n, 2)

    def test_hu06_borrador_requiere_confirmacion_y_no_envia(self):
        self.login()
        t = self.csrf("/verificaciones/nueva?centro=3")
        self.c.post("/verificaciones/nueva", data={"csrf": t, "centro_id": 3, "alcance": "general",
                                                   "area": "redes", "diagnostico": "Caída de enlaces del bloque 33."})
        r = self.c.post("/verificaciones/1/caso", data={"csrf": t, "motivo": "Afectación general del bloque", "prioridad": "Alta"},
                        follow_redirects=True)
        self.assertIn("confirmar explícitamente", r.get_data(as_text=True))
        r = self.c.post("/verificaciones/1/caso", data={"csrf": t, "motivo": "Afectación general del bloque",
                                                        "prioridad": "Alta", "confirmo": "si"}, follow_redirects=True)
        self.assertIn("No se envía a Aranda", r.get_data(as_text=True))
        # El técnico no puede marcarlo como registrado; el coordinador sí, con referencia
        self.assertEqual(self.c.post("/casos/1", data={"csrf": t, "accion": "registrar", "referencia": "A-1"}).status_code, 403)
        self.c.post("/logout", data={"csrf": t})
        self.login("coord")
        t = self.csrf("/casos")
        self.c.post("/casos/1", data={"csrf": t, "accion": "registrar", "referencia": "ARD-2026-001"})
        with self.app.app_context():
            k = self.db().execute("SELECT * FROM casos WHERE id=1").fetchone()
        self.assertEqual(k["referencia_aranda"], "ARD-2026-001")
        self.assertIn("Registrado", k["estado"])


class TestLogica(BaseTest):
    def escenario(self, eventos):
        """Centro aislado para observar duración y recurrencia sin datos del seed."""
        with self.app.app_context():
            db = self.db()
            db.execute("INSERT INTO centros(codigo,nombre,frecuencia_reporte_min,creado_en) VALUES ('REG','Regresión',15,?)",
                       (appmod.ahora().strftime(appmod.FMT),))
            cid = db.execute("SELECT id FROM centros WHERE codigo='REG'").fetchone()[0]
            for tipo, fecha in eventos:
                db.execute("INSERT INTO eventos(centro_id,tipo,ocurrido_en,recibido_en,origen) VALUES (?,?,?,?,'simulado')",
                           (cid, tipo, fecha, fecha))
            db.commit()
        self.login()
        return self.c.get(f"/centros/{cid}").get_data(as_text=True)

    def test_low_repetidos_conservan_inicio_y_un_solo_episodio(self):
        now = appmod.parse_dt("2026-11-20 12:00:00")
        with patch.object(appmod, "ahora", return_value=now):
            html = self.escenario([("LOW", "2026-11-20 11:40:00"),
                                   ("LOW", "2026-11-20 11:59:00")])
        self.assertIn("Sin alimentación EPM (20 min)", html)
        self.assertIn("1 episodios iniciados en la ventana", html)
        self.assertRegex(html, r'Criticidad</dt><dd><span class="status alert">Alta</span>')

    def test_recuperacion_y_nuevo_corte_forman_dos_episodios(self):
        now = appmod.parse_dt("2026-11-20 12:00:00")
        with patch.object(appmod, "ahora", return_value=now):
            html = self.escenario([("LOW", "2026-11-20 11:00:00"),
                                   ("HIGH", "2026-11-20 11:10:00"),
                                   ("LOW", "2026-11-20 11:40:00"),
                                   ("LOW", "2026-11-20 11:59:00")])
        self.assertIn("2 episodios iniciados en la ventana", html)
        self.assertIn("Sin alimentación EPM (20 min)", html)

    def test_corte_anterior_a_ventana_no_suma_nueva_recurrencia(self):
        now = appmod.parse_dt("2026-11-20 12:00:00")
        with patch.object(appmod, "ahora", return_value=now):
            html = self.escenario([("LOW", "2026-11-10 12:00:00"),
                                   ("LOW", "2026-11-20 11:59:00")])
        self.assertIn("Sin alimentación EPM (14400 min)", html)
        self.assertIn("0 episodios iniciados en la ventana", html)

    def test_eventos_desordenados_se_agrupan_por_ocurrencia(self):
        now = appmod.parse_dt("2026-11-20 12:00:00")
        with patch.object(appmod, "ahora", return_value=now):
            html = self.escenario([("HIGH", "2026-11-20 11:50:00"),
                                   ("LOW", "2026-11-20 11:40:00"),
                                   ("LOW", "2026-11-20 11:45:00")])
        self.assertIn("Con alimentación EPM", html)
        self.assertIn("10.0 min", html)
        self.assertIn("1 episodios iniciados en la ventana", html)

    def test_api_rechaza_json_invalido_y_fechas_futuras(self):
        headers = {"X-API-Key": "clave-de-prueba"}
        for body in ([1], {"codigo_centro": "CT-B19-P1", "tipo": "LOW", "ocurrido_en": 42},
                     {"codigo_centro": "CT-B19-P1", "tipo": "LOW", "ocurrido_en": "2099-01-01 00:00:00"}):
            with self.subTest(body=body):
                self.assertEqual(self.c.post("/api/eventos", headers=headers, json=body).status_code, 400)

    def test_verificacion_rechaza_evento_de_otro_centro(self):
        self.login()
        with self.app.app_context():
            ev = self.db().execute("SELECT id FROM eventos WHERE centro_id != 1 LIMIT 1").fetchone()[0]
        r = self.c.post("/verificaciones/nueva", data={"csrf": self.csrf("/verificaciones/nueva"),
            "centro_id": 1, "evento_id": ev, "alcance": "incierto", "area": "redes",
            "diagnostico": "Revisión de prueba del centro"}, follow_redirects=True)
        self.assertIn("El evento debe existir y pertenecer al centro", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(self.db().execute("SELECT COUNT(*) FROM verificaciones").fetchone()[0], 0)

    def test_reglas_rechazan_ventana_o_recurrencia_no_positivas(self):
        self.login("coord")
        for campo, valor in (("ventana_dias", 0), ("repeticiones_alta", -1)):
            datos = dict(appmod.REGLAS_DEFECTO, csrf=self.csrf("/criticidad"), accion="guardar")
            datos[campo] = valor
            r = self.c.post("/criticidad", data=datos, follow_redirects=True)
            self.assertIn("deben ser mayores que cero", r.get_data(as_text=True))
            with self.app.app_context():
                self.assertEqual(self.db().execute("SELECT valor FROM reglas WHERE clave=?", (campo,)).fetchone()[0],
                                 appmod.REGLAS_DEFECTO[campo])

    def test_episodios_emparejan_low_high(self):
        with self.app.app_context():
            db = self.db()
            db.execute("INSERT INTO centros(codigo, nombre, frecuencia_reporte_min, creado_en) VALUES ('EP','EP',15,'2026-01-01 00:00:00')")
            cid = db.execute("SELECT id FROM centros WHERE codigo='EP'").fetchone()[0]
            for tipo, t in (("LOW", "2026-11-01 10:00:00"), ("HIGH", "2026-11-01 10:07:30"), ("HIGH", "2026-11-01 11:00:00")):
                db.execute("INSERT INTO eventos(centro_id, tipo, ocurrido_en, recibido_en, origen) VALUES (?,?,?,?, 'manual')",
                           (cid, tipo, t, t))
            db.commit()
        self.login()
        html = self.c.get(f"/centros/{cid}").get_data(as_text=True)
        self.assertIn("7.5 min", html)
        self.assertEqual(html.count("2026-11-01 11:00:00</td>"), 0)  # HIGH sin LOW previo no crea episodio


if __name__ == "__main__":
    unittest.main()
