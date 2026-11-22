"""Escenarios de aceptación de tendencias y temporizadores simulados."""
from unittest.mock import patch
from test_app import BaseTest, appmod


class TestCierre(BaseTest):
    def setUp(self):
        super().setUp()
        self.now = appmod.parse_dt('2026-11-20 12:00:00')
        with self.app.app_context():
            db = self.db()
            db.execute("INSERT INTO centros(codigo,nombre,creado_en) VALUES ('CIERRE','Centro ficticio','2026-11-01 00:00:00')")
            self.cid = db.execute("SELECT id FROM centros WHERE codigo='CIERRE'").fetchone()[0]
            db.commit()

    def eventos(self, pares):
        with self.app.app_context():
            db = self.db()
            for tipo, fecha in pares:
                db.execute("INSERT INTO eventos(centro_id,tipo,ocurrido_en,recibido_en,origen) VALUES (?,?,?,?,'simulado')", (self.cid,tipo,fecha,fecha))
            db.commit()

    def aviso(self, hora):
        with patch.object(appmod, 'ahora', return_value=self.now):
            return self.c.get(f'/avisos-simulados?centro={self.cid}&evaluado_en=2026-11-20T{hora}').get_data(as_text=True)

    def test_avisos_umbral_y_low_repetido(self):
        self.eventos([('LOW','2026-11-20 11:40:00'),('LOW','2026-11-20 11:44:00')])
        self.login()
        for hora, generados in [('11:44:00',0),('11:45:00',1),('11:49:00',1),('11:50:00',2)]:
            with self.subTest(hora=hora):
                html = self.aviso(hora)
                self.assertEqual(html.count('>Generado (simulado)</span>'), generados)
                self.assertEqual(html.count('>Pendiente</span>'),2-generados)

    def test_high_cancela_pendiente_sin_borrar_aviso_superado(self):
        self.eventos([('LOW','2026-11-20 11:40:00'),('HIGH','2026-11-20 11:47:00')])
        self.login()
        html = self.aviso('11:55:00')
        self.assertEqual(html.count('>Generado (simulado)</span>'),1)
        self.assertEqual(html.count('>Cancelado por retorno</span>'),1)
        self.assertEqual(self.aviso('11:44:00').count('>Pendiente</span>'),2)

    def test_retorno_en_umbral_cancela_y_silencio_no_inventa_corte(self):
        self.login()
        self.assertIn('No hay episodios LOW', self.aviso('11:55:00'))
        self.eventos([('LOW','2026-11-20 11:40:00'),('HIGH','2026-11-20 11:45:00')])
        self.assertEqual(self.aviso('11:55:00').count('>Cancelado por retorno</span>'),2)

    def test_tendencias_periodo_centro_y_episodios_sin_duplicar(self):
        self.eventos([('LOW','2026-11-19 10:00:00'),('LOW','2026-11-20 10:00:00'),('HIGH','2026-11-20 10:05:00'),('LOW','2026-11-20 11:40:00')])
        self.login('coord')
        with patch.object(appmod, 'ahora', return_value=self.now):
            r = self.c.get(f'/tendencias?centro={self.cid}&desde=2026-11-20&hasta=2026-11-20')
        self.assertEqual(r.status_code,200)
        html = r.get_data(as_text=True)
        self.assertIn('id="total-episodios">1</strong>',html)
        self.assertIn('<strong class="value">3</strong>',html)  # tres señales, un nuevo episodio
        self.assertNotIn('CT-B33-P2</td>',html)

    def test_filtros_invalidos_y_permiso(self):
        self.login('tec')
        self.assertEqual(self.c.get('/tendencias').status_code,403)
        self.assertEqual(self.c.get('/avisos-simulados?evaluado_en=2099-01-01T00:00').status_code,400)
        self.assertEqual(self.c.get('/avisos-simulados?centro=no').status_code,400)
        self.c.post('/logout',data={'csrf':self.csrf('/eventos')})
        self.login('coord')
        for q in ['desde=2026-11-20&hasta=2026-11-19','desde=error','desde=2026-01-01&hasta=2026-11-20','centro=999999']:
            self.assertEqual(self.c.get('/tendencias?'+q).status_code,400)

    def test_simulacion_no_modifica_eventos_ni_crea_casos(self):
        self.eventos([('LOW','2026-11-20 11:40:00')])
        self.login()
        with self.app.app_context():
            antes = {t:self.db().execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('eventos','casos','auditoria')}
        self.aviso('11:55:00')
        self.aviso('11:55:00')
        with self.app.app_context():
            despues = {t:self.db().execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in antes}
        self.assertEqual(antes,despues)
