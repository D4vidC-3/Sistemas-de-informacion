"""Centro de Operaciones de Redes - EAFIT (Entrega 3, Sistemas de Información).

Aplicación web para registrar y consultar eventos de alimentación EPM de los
centros de cableado, distinguir estado eléctrico de estado de comunicación,
clasificar criticidad, registrar la verificación humana y preparar borradores
de caso para Aranda (sin integración automática).

Todos los datos de la aplicación son ficticios / de prueba.
"""
import csv
import io
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

import click
from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("America/Bogota")
FMT = "%Y-%m-%d %H:%M:%S"

TIPOS_EVENTO = {
    "LOW": "Pérdida de alimentación EPM (señal LOW)",
    "HIGH": "Retorno de alimentación EPM (señal HIGH)",
    "EN_LINEA": "Reporte de salud del dispositivo (EN_LINEA)",
    "ENERGIA_RESTABLECIDA": "Reinicio / energía restablecida del dispositivo",
}
ORIGENES = {"manual": "Registro manual", "simulado": "Simulación de prueba", "api": "API (dispositivo)"}
ALCANCES = {"sectorizado": "Sectorizado", "general": "General", "incierto": "Incierto"}
AREAS = {"redes": "Infraestructura y Operaciones de Redes",
         "campus": "Gestión del Campus (eléctrico)",
         "mesa": "Mesa de Servicio"}
ESTADOS_VERIF = ["Abierta", "En curso", "Cerrada"]
REGLAS_DEFECTO = {
    "umbral_media_min": 5,
    "umbral_alta_min": 10,
    "umbral_critica_min": 30,
    "repeticiones_alta": 3,
    "ventana_dias": 7,
}


def ahora():
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def parse_dt(txt):
    if not txt:
        return None
    txt = txt.strip().replace("T", " ")
    for fmt in (FMT, "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(txt, fmt)
        except ValueError:
            pass
    return None


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "instance", "redes.db")),
        API_KEY=os.environ.get("API_KEY", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    # ------------------------------------------------------------------ BD
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
            db.executescript(f.read())
        for k, v in REGLAS_DEFECTO.items():
            db.execute("INSERT OR IGNORE INTO reglas(clave, valor) VALUES (?, ?)", (k, v))
        db.commit()

    def auditar(accion, entidad, entidad_id=None, detalle=""):
        db = get_db()
        db.execute(
            "INSERT INTO auditoria(usuario_id, accion, entidad, entidad_id, detalle, fecha) VALUES (?,?,?,?,?,?)",
            (session.get("uid"), accion, entidad, entidad_id, detalle, ahora().strftime(FMT)),
        )

    app.get_db, app.init_db = get_db, init_db

    # ------------------------------------------------------- seguridad
    def login_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if not g.user:
                return redirect(url_for("login", next=request.path))
            return view(*a, **kw)
        return wrapped

    def role_required(*roles):
        def deco(view):
            @wraps(view)
            @login_required
            def wrapped(*a, **kw):
                if g.user["rol"] not in roles:
                    abort(403)
                return view(*a, **kw)
            return wrapped
        return deco

    @app.before_request
    def cargar_usuario_y_csrf():
        uid = session.get("uid")
        g.user = None
        if uid:
            g.user = get_db().execute("SELECT * FROM usuarios WHERE id=? AND activo=1", (uid,)).fetchone()
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method == "POST" and not request.path.startswith("/api/"):
            if request.form.get("csrf") != session.get("csrf"):
                abort(400, "Token CSRF inválido")

    @app.context_processor
    def globales():
        return dict(csrf=session.get("csrf"), user=g.get("user"), TIPOS=TIPOS_EVENTO,
                    ORIGENES=ORIGENES, ALCANCES=ALCANCES, AREAS=AREAS)

    # ----------------------------------------------------- lógica de negocio
    def reglas():
        return {r["clave"]: int(r["valor"]) for r in get_db().execute("SELECT * FROM reglas")}

    def clasificar(duracion_min, repeticiones, rg=None):
        """Clasifica criticidad según reglas configurables (HU-05)."""
        rg = rg or reglas()
        if duracion_min is None:  # centro con alimentación: solo cuenta recurrencia
            return "Media" if repeticiones >= rg["repeticiones_alta"] else "Sin alerta"
        if duracion_min >= rg["umbral_critica_min"] or (
                duracion_min >= rg["umbral_alta_min"] and repeticiones >= rg["repeticiones_alta"]):
            return "Crítica"
        if duracion_min >= rg["umbral_alta_min"] or repeticiones >= rg["repeticiones_alta"]:
            return "Alta"
        if duracion_min >= rg["umbral_media_min"]:
            return "Media"
        return "Baja"

    def estado_centro(c, rg=None, now=None):
        """Estado eléctrico y de comunicación por separado (HU-03)."""
        db, rg, now = get_db(), rg or reglas(), now or ahora()
        ult_elec = db.execute(
            "SELECT * FROM eventos WHERE centro_id=? AND tipo IN ('LOW','HIGH') ORDER BY ocurrido_en DESC, id DESC LIMIT 1",
            (c["id"],)).fetchone()
        ult_any = db.execute(
            "SELECT * FROM eventos WHERE centro_id=? ORDER BY ocurrido_en DESC, id DESC LIMIT 1", (c["id"],)).fetchone()
        desde = (now - timedelta(days=rg["ventana_dias"])).strftime(FMT)
        cortes = episodios(c["id"], limite=None)
        # LOW repetidos durante el mismo corte no abren otro episodio.
        reps = sum(ep["inicio"] >= desde for ep in cortes)
        if ult_elec is None:
            elec, elec_cls, dur = "Sin dato eléctrico", "offline", None
        elif ult_elec["tipo"] == "LOW":
            inicio = cortes[0]["inicio"]
            dur = max(0, int((now - parse_dt(inicio)).total_seconds() // 60))
            elec, elec_cls = f"Sin alimentación EPM ({dur} min)", "alert"
        else:
            elec, elec_cls, dur = "Con alimentación EPM", "ok", None
        if not c["frecuencia_reporte_min"]:
            com, com_cls = "Frecuencia no configurada", "medium"
        elif ult_any is None:
            com, com_cls = "Sin reportes", "offline"
        else:
            mins = (now - parse_dt(ult_any["ocurrido_en"])).total_seconds() / 60
            if mins > c["frecuencia_reporte_min"]:
                com, com_cls = "Sin comunicación", "offline"
            else:
                com, com_cls = "Comunicando", "ok"
        crit = clasificar(dur, reps, rg) if ult_elec is not None else "Sin alerta"
        return dict(elec=elec, elec_cls=elec_cls, com=com, com_cls=com_cls, crit=crit, reps=reps,
                    ultimo=ult_any["ocurrido_en"] if ult_any else None)

    def episodios(centro_id, limite=20, hasta=None):
        """Empareja LOW -> siguiente HIGH (transiciones != episodios)."""
        rows = get_db().execute(
            "SELECT * FROM eventos WHERE centro_id=? AND tipo IN ('LOW','HIGH') "
            "AND ocurrido_en<=? ORDER BY ocurrido_en, id",
            (centro_id, (hasta or ahora()).strftime(FMT))).fetchall()
        eps, abierto = [], None
        for r in rows:
            if r["tipo"] == "LOW":
                if abierto is None:
                    abierto = r
            elif abierto is not None:
                ini, fin = parse_dt(abierto["ocurrido_en"]), parse_dt(r["ocurrido_en"])
                eps.append(dict(inicio=abierto["ocurrido_en"], fin=r["ocurrido_en"],
                                minutos=round((fin - ini).total_seconds() / 60, 1)))
                abierto = None
        if abierto is not None:
            eps.append(dict(inicio=abierto["ocurrido_en"], fin=None, minutos=None))
        return list(reversed(eps))[:limite]

    def centro_filtrado():
        valor = request.args.get("centro", "")
        if not valor:
            return None
        try:
            cid = int(valor)
        except ValueError:
            abort(400, "Centro inválido")
        if not get_db().execute("SELECT 1 FROM centros WHERE id=? AND activo=1", (cid,)).fetchone():
            abort(400, "Centro inválido")
        return cid

    @app.route("/tendencias")
    @role_required("coordinador")
    def tendencias():
        now = ahora()
        desde = request.args.get("desde", (now - timedelta(days=6)).strftime("%Y-%m-%d"))
        hasta = request.args.get("hasta", now.strftime("%Y-%m-%d"))
        try:
            ini, fin = datetime.strptime(desde, "%Y-%m-%d"), datetime.strptime(hasta, "%Y-%m-%d")
        except ValueError:
            abort(400, "Fechas inválidas")
        if fin < ini or (fin - ini).days > 89 or fin.date() > now.date():
            abort(400, "Seleccione un periodo pasado de entre 1 y 90 días")
        cid = centro_filtrado()
        centros = get_db().execute("SELECT * FROM centros WHERE activo=1 ORDER BY codigo").fetchall()
        dias = {(ini + timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range((fin-ini).days+1)}
        por_centro, total_senales, abiertos = [], 0, 0
        for c in centros:
            if cid is not None and c["id"] != cid:
                continue
            eps = [e for e in episodios(c["id"], None, now) if desde <= e["inicio"][:10] <= hasta]
            for e in eps:
                dias[e["inicio"][:10]] += 1
            senales = get_db().execute(
                "SELECT COUNT(*) FROM eventos WHERE centro_id=? AND tipo IN ('LOW','HIGH') "
                "AND ocurrido_en>=? AND ocurrido_en<=? AND ocurrido_en<?",
                (c["id"], ini.strftime(FMT), now.strftime(FMT), (fin+timedelta(days=1)).strftime(FMT))).fetchone()[0]
            total_senales += senales
            abiertos += sum(e["fin"] is None for e in eps)
            por_centro.append(dict(codigo=c["codigo"], episodios=len(eps), senales=senales))
        return render_template("tendencias.html", centros=centros, cid=cid, desde=desde, hasta=hasta,
            dias=dias, por_centro=por_centro, total=sum(dias.values()), senales=total_senales,
            abiertos=abiertos, max_dia=max(dias.values(), default=0) or 1,
            max_centro=max((c["episodios"] for c in por_centro), default=0) or 1)

    @app.route("/avisos-simulados")
    @login_required
    def avisos_simulados():
        now = ahora()
        valor = request.args.get("evaluado_en", "")
        try:
            evaluado = parse_dt(valor.replace("T", " ")) if valor else now
        except (ValueError, TypeError):
            abort(400, "Fecha de evaluación inválida")
        if evaluado is None or evaluado > now:
            abort(400, "La evaluación no puede estar en el futuro")
        cid = centro_filtrado()
        centros = get_db().execute("SELECT * FROM centros WHERE activo=1 ORDER BY codigo").fetchall()
        filas = []
        for c in centros:
            if cid is not None and c["id"] != cid:
                continue
            for e in episodios(c["id"], 20, evaluado):
                inicio = parse_dt(e["inicio"])
                fin = parse_dt(e["fin"]) if e["fin"] else None
                avisos = []
                for minutos in (5, 10):
                    vence = inicio + timedelta(minutes=minutos)
                    if fin is not None and fin <= vence:
                        estado = "Cancelado por retorno"
                    elif evaluado >= vence:
                        estado = "Generado (simulado)"
                    else:
                        estado = "Pendiente"
                    avisos.append(dict(minutos=minutos, vence=vence.strftime(FMT), estado=estado))
                filas.append(dict(codigo=c["codigo"], inicio=e["inicio"], fin=e["fin"], avisos=avisos))
        return render_template("avisos_simulados.html", centros=centros, cid=cid, filas=filas,
                               evaluado=evaluado.strftime(FMT))

    def crit_cls(nivel):
        return {"Crítica": "alert", "Alta": "alert", "Media": "medium", "Baja": "blue"}.get(nivel, "ok")

    app.jinja_env.globals["crit_cls"] = crit_cls

    def registrar_evento(centro_id, tipo, ocurrido_en, origen, nota="", usuario_id=None):
        db = get_db()
        dup = db.execute("SELECT id FROM eventos WHERE centro_id=? AND tipo=? AND ocurrido_en=?",
                         (centro_id, tipo, ocurrido_en)).fetchone()
        if dup:
            return dup["id"], False
        cur = db.execute(
            "INSERT INTO eventos(centro_id, tipo, ocurrido_en, recibido_en, origen, nota, registrado_por) VALUES (?,?,?,?,?,?,?)",
            (centro_id, tipo, ocurrido_en, ahora().strftime(FMT), origen, nota, usuario_id))
        return cur.lastrowid, True

    # ----------------------------------------------------------- rutas
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            u = get_db().execute("SELECT * FROM usuarios WHERE usuario=? AND activo=1",
                                 (request.form.get("usuario", "").strip(),)).fetchone()
            if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
                session.clear()
                session["uid"] = u["id"]
                session.permanent = True
                g.user = u
                auditar("login", "usuario", u["id"])
                get_db().commit()
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("dashboard"))
            flash("Usuario o contraseña incorrectos.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        db, rg = get_db(), reglas()
        centros = db.execute("SELECT * FROM centros WHERE activo=1 ORDER BY codigo").fetchall()
        filas = [dict(c=c, e=estado_centro(c, rg)) for c in centros]
        stats = dict(
            total=len(filas),
            sin_epm=sum(1 for f in filas if f["e"]["elec_cls"] == "alert"),
            sin_com=sum(1 for f in filas if f["e"]["com"] == "Sin comunicación"),
            verif_abiertas=db.execute("SELECT COUNT(*) FROM verificaciones WHERE estado!='Cerrada'").fetchone()[0],
        )
        orden = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}
        filas.sort(key=lambda f: (orden.get(f["e"]["crit"], 9), f["c"]["codigo"]))
        recientes = db.execute(
            "SELECT e.*, c.codigo FROM eventos e JOIN centros c ON c.id=e.centro_id ORDER BY e.ocurrido_en DESC, e.id DESC LIMIT 8"
        ).fetchall()
        return render_template("dashboard.html", filas=filas, stats=stats, recientes=recientes)

    # HU-01 centros
    @app.route("/centros")
    @login_required
    def centros():
        q = request.args.get("q", "").strip()
        sql, args = "SELECT * FROM centros WHERE activo=1", []
        if q:
            sql += " AND (codigo LIKE ? OR nombre LIKE ? OR ubicacion LIKE ?)"
            args = [f"%{q}%"] * 3
        rows = get_db().execute(sql + " ORDER BY codigo", args).fetchall()
        rg = reglas()
        return render_template("centros.html", filas=[dict(c=c, e=estado_centro(c, rg)) for c in rows], q=q)

    @app.route("/centros/nuevo", methods=["POST"])
    @role_required("coordinador")
    def centro_nuevo():
        f = request.form
        codigo = f.get("codigo", "").strip().upper()
        if not codigo or not f.get("nombre", "").strip():
            flash("Código y nombre son obligatorios.", "error")
            return redirect(url_for("centros"))
        try:
            freq = int(f.get("frecuencia_reporte_min") or 0) or None
        except ValueError:
            freq = None
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO centros(codigo, nombre, ubicacion, frecuencia_reporte_min, creado_en) VALUES (?,?,?,?,?)",
                (codigo, f["nombre"].strip(), f.get("ubicacion", "").strip(), freq, ahora().strftime(FMT)))
        except sqlite3.IntegrityError:
            flash(f"Ya existe un centro con código {codigo}.", "error")
            return redirect(url_for("centros"))
        auditar("crear", "centro", cur.lastrowid, codigo)
        db.commit()
        flash(f"Centro {codigo} registrado.", "ok")
        return redirect(url_for("centro_detalle", cid=cur.lastrowid))

    @app.route("/centros/<int:cid>")
    @login_required
    def centro_detalle(cid):
        db = get_db()
        c = db.execute("SELECT * FROM centros WHERE id=?", (cid,)).fetchone() or abort(404)
        eventos = db.execute("SELECT * FROM eventos WHERE centro_id=? ORDER BY ocurrido_en DESC, id DESC LIMIT 15",
                             (cid,)).fetchall()
        verifs = db.execute(
            "SELECT v.*, u.nombre AS autor FROM verificaciones v JOIN usuarios u ON u.id=v.autor_id WHERE centro_id=? ORDER BY creado_en DESC",
            (cid,)).fetchall()
        return render_template("centro_detalle.html", c=c, e=estado_centro(c), eventos=eventos,
                               episodios=episodios(cid), verifs=verifs)

    # HU-02 eventos
    @app.route("/eventos", methods=["GET", "POST"])
    @login_required
    def eventos():
        db = get_db()
        if request.method == "POST":
            f = request.form
            c = db.execute("SELECT * FROM centros WHERE id=?", (f.get("centro_id"),)).fetchone()
            tipo, origen = f.get("tipo"), f.get("origen", "manual")
            oc = parse_dt(f.get("ocurrido_en")) or ahora()
            if not c or tipo not in TIPOS_EVENTO or origen not in ("manual", "simulado"):
                flash("Datos del evento inválidos.", "error")
            elif oc > ahora() + timedelta(minutes=1):
                flash("La fecha de ocurrencia no puede estar en el futuro.", "error")
            else:
                eid, nuevo = registrar_evento(c["id"], tipo, oc.strftime(FMT), origen,
                                              f.get("nota", "").strip()[:300], g.user["id"])
                if nuevo:
                    auditar("crear", "evento", eid, f"{c['codigo']} {tipo}")
                    db.commit()
                    flash(f"Evento {tipo} registrado para {c['codigo']}.", "ok")
                else:
                    flash("Evento duplicado: ya existía un registro idéntico; no se guardó de nuevo.", "error")
            return redirect(url_for("eventos"))
        centros_ = db.execute("SELECT * FROM centros WHERE activo=1 ORDER BY codigo").fetchall()
        recientes = db.execute(
            "SELECT e.*, c.codigo, u.nombre AS autor FROM eventos e JOIN centros c ON c.id=e.centro_id "
            "LEFT JOIN usuarios u ON u.id=e.registrado_por ORDER BY e.recibido_en DESC, e.id DESC LIMIT 10").fetchall()
        return render_template("eventos.html", centros=centros_, recientes=recientes,
                               ahora=ahora().strftime("%Y-%m-%dT%H:%M"))

    # HU-04 historial
    def _filtrar_historial(args):
        sql = ("SELECT e.*, c.codigo, c.nombre AS centro FROM eventos e JOIN centros c ON c.id=e.centro_id WHERE 1=1")
        p = []
        if args.get("centro"):
            sql += " AND c.id=?"; p.append(args["centro"])
        if args.get("tipo") in TIPOS_EVENTO:
            sql += " AND e.tipo=?"; p.append(args["tipo"])
        if parse_dt(args.get("desde", "") + " 00:00"):
            sql += " AND e.ocurrido_en>=?"; p.append(args["desde"] + " 00:00:00")
        if parse_dt(args.get("hasta", "") + " 00:00"):
            sql += " AND e.ocurrido_en<=?"; p.append(args["hasta"] + " 23:59:59")
        return get_db().execute(sql + " ORDER BY e.ocurrido_en DESC, e.id DESC", p).fetchall()

    @app.route("/historial")
    @login_required
    def historial():
        rows = _filtrar_historial(request.args)
        centros_ = get_db().execute("SELECT id, codigo FROM centros ORDER BY codigo").fetchall()
        return render_template("historial.html", rows=rows[:300], total=len(rows), centros=centros_, f=request.args)

    @app.route("/historial.csv")
    @login_required
    def historial_csv():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "centro", "tipo", "ocurrido_en", "recibido_en", "origen", "nota"])
        for r in _filtrar_historial(request.args):
            w.writerow([r["id"], r["codigo"], r["tipo"], r["ocurrido_en"], r["recibido_en"], r["origen"], r["nota"]])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=historial_eventos.csv"})

    # HU-05 criticidad
    @app.route("/criticidad", methods=["GET", "POST"])
    @login_required
    def criticidad():
        db, resultado = get_db(), None
        if request.method == "POST" and request.form.get("accion") == "guardar":
            if g.user["rol"] != "coordinador":
                abort(403)
            nuevas = {}
            for k in REGLAS_DEFECTO:
                try:
                    nuevas[k] = int(request.form.get(k))
                except (TypeError, ValueError):
                    flash("Todos los parámetros deben ser números enteros.", "error")
                    return redirect(url_for("criticidad"))
            if not (0 < nuevas["umbral_media_min"] < nuevas["umbral_alta_min"] < nuevas["umbral_critica_min"]):
                flash("Los umbrales deben cumplir: media < alta < crítica.", "error")
                return redirect(url_for("criticidad"))
            if nuevas["repeticiones_alta"] < 1 or nuevas["ventana_dias"] < 1:
                flash("La recurrencia y su ventana deben ser mayores que cero.", "error")
                return redirect(url_for("criticidad"))
            for k, v in nuevas.items():
                db.execute("UPDATE reglas SET valor=? WHERE clave=?", (v, k))
            auditar("actualizar", "reglas", None, str(nuevas))
            db.commit()
            flash("Reglas de criticidad actualizadas.", "ok")
            return redirect(url_for("criticidad"))
        if request.method == "POST" and request.form.get("accion") == "probar":
            try:
                d, r = int(request.form.get("duracion")), int(request.form.get("repeticiones"))
                resultado = dict(d=d, r=r, nivel=clasificar(d, r))
            except (TypeError, ValueError):
                flash("Ingrese números enteros para probar la regla.", "error")
        return render_template("criticidad.html", rg=reglas(), resultado=resultado)

    # HU-09 verificación humana
    @app.route("/verificaciones")
    @login_required
    def verificaciones():
        estado = request.args.get("estado", "")
        sql = ("SELECT v.*, c.codigo, u.nombre AS autor, "
               "(SELECT COUNT(*) FROM casos k WHERE k.verificacion_id=v.id) AS ncasos "
               "FROM verificaciones v JOIN centros c ON c.id=v.centro_id JOIN usuarios u ON u.id=v.autor_id")
        p = []
        if estado in ESTADOS_VERIF:
            sql += " WHERE v.estado=?"; p.append(estado)
        rows = get_db().execute(sql + " ORDER BY v.creado_en DESC", p).fetchall()
        return render_template("verificaciones.html", rows=rows, estado=estado, estados=ESTADOS_VERIF)

    @app.route("/verificaciones/nueva", methods=["GET", "POST"])
    @login_required
    def verificacion_nueva():
        db = get_db()
        if request.method == "POST":
            f = request.form
            c = db.execute("SELECT * FROM centros WHERE id=?", (f.get("centro_id"),)).fetchone()
            diag = f.get("diagnostico", "").strip()
            if not c or len(diag) < 10 or f.get("alcance") not in ALCANCES or f.get("area") not in AREAS:
                flash("Complete centro, alcance, área y un diagnóstico de al menos 10 caracteres.", "error")
                return redirect(url_for("verificacion_nueva", centro=f.get("centro_id"), evento=f.get("evento_id")))
            ev = f.get("evento_id") or None
            if ev is not None and not db.execute(
                    "SELECT 1 FROM eventos WHERE id=? AND centro_id=?", (ev, c["id"])).fetchone():
                flash("El evento debe existir y pertenecer al centro seleccionado.", "error")
                return redirect(url_for("verificacion_nueva", centro=c["id"]))
            cur = db.execute(
                "INSERT INTO verificaciones(centro_id, evento_id, autor_id, creado_en, diagnostico, alcance, area_responsable, estado) "
                "VALUES (?,?,?,?,?,?,?, 'Abierta')",
                (c["id"], ev, g.user["id"], ahora().strftime(FMT), diag[:1000], f["alcance"], f["area"]))
            auditar("crear", "verificacion", cur.lastrowid, c["codigo"])
            db.commit()
            flash("Verificación registrada.", "ok")
            return redirect(url_for("verificacion_detalle", vid=cur.lastrowid))
        centros_ = db.execute("SELECT * FROM centros WHERE activo=1 ORDER BY codigo").fetchall()
        sel = request.args.get("centro", type=int)
        evs = db.execute("SELECT * FROM eventos WHERE centro_id=? ORDER BY ocurrido_en DESC LIMIT 10", (sel,)).fetchall() if sel else []
        return render_template("verificacion_nueva.html", centros=centros_, sel=sel, evs=evs,
                               evento=request.args.get("evento", type=int))

    @app.route("/verificaciones/<int:vid>", methods=["GET", "POST"])
    @login_required
    def verificacion_detalle(vid):
        db = get_db()
        v = db.execute("SELECT v.*, c.codigo, c.nombre AS centro, u.nombre AS autor, uc.nombre AS cerrador "
                       "FROM verificaciones v JOIN centros c ON c.id=v.centro_id JOIN usuarios u ON u.id=v.autor_id "
                       "LEFT JOIN usuarios uc ON uc.id=v.cerrado_por WHERE v.id=?", (vid,)).fetchone() or abort(404)
        if request.method == "POST":
            nuevo = request.form.get("estado")
            resultado = request.form.get("resultado", "").strip()
            if v["estado"] == "Cerrada":
                flash("La verificación ya está cerrada.", "error")
            elif nuevo not in ESTADOS_VERIF:
                flash("Estado inválido.", "error")
            elif nuevo == "Cerrada" and len(resultado) < 10:
                flash("Para cerrar debe registrar el resultado verificado del servicio (mín. 10 caracteres).", "error")
            else:
                if nuevo == "Cerrada":
                    db.execute("UPDATE verificaciones SET estado=?, resultado=?, cerrado_en=?, cerrado_por=? WHERE id=?",
                               (nuevo, resultado[:1000], ahora().strftime(FMT), g.user["id"], vid))
                else:
                    db.execute("UPDATE verificaciones SET estado=? WHERE id=?", (nuevo, vid))
                auditar("estado", "verificacion", vid, nuevo)
                db.commit()
                flash(f"Verificación actualizada a «{nuevo}».", "ok")
            return redirect(url_for("verificacion_detalle", vid=vid))
        ev = db.execute("SELECT * FROM eventos WHERE id=?", (v["evento_id"],)).fetchone() if v["evento_id"] else None
        casos_ = db.execute("SELECT k.*, u.nombre AS autor FROM casos k JOIN usuarios u ON u.id=k.creado_por "
                            "WHERE verificacion_id=? ORDER BY creado_en DESC", (vid,)).fetchall()
        hist = db.execute("SELECT a.*, u.nombre FROM auditoria a LEFT JOIN usuarios u ON u.id=a.usuario_id "
                          "WHERE entidad='verificacion' AND entidad_id=? ORDER BY a.id", (vid,)).fetchall()
        return render_template("verificacion_detalle.html", v=v, ev=ev, casos=casos_, hist=hist, estados=ESTADOS_VERIF)

    # HU-06-SIM borrador de caso
    @app.route("/verificaciones/<int:vid>/caso", methods=["POST"])
    @login_required
    def caso_nuevo(vid):
        db = get_db()
        v = db.execute("SELECT * FROM verificaciones WHERE id=?", (vid,)).fetchone() or abort(404)
        f = request.form
        if f.get("confirmo") != "si":
            flash("Debe confirmar explícitamente que la decisión de abrir caso es humana.", "error")
        elif len(f.get("motivo", "").strip()) < 10 or f.get("prioridad") not in ("Baja", "Media", "Alta", "Crítica"):
            flash("Indique motivo (mín. 10 caracteres) y prioridad.", "error")
        else:
            cur = db.execute(
                "INSERT INTO casos(verificacion_id, motivo, prioridad, creado_por, creado_en, estado) VALUES (?,?,?,?,?, 'Borrador')",
                (v["id"], f["motivo"].strip()[:1000], f["prioridad"], g.user["id"], ahora().strftime(FMT)))
            auditar("crear", "caso", cur.lastrowid, f"borrador para verificación {vid}")
            db.commit()
            flash("Borrador de caso creado. No se envía a Aranda: debe registrarse manualmente.", "ok")
        return redirect(url_for("verificacion_detalle", vid=vid))

    @app.route("/casos")
    @login_required
    def casos():
        rows = get_db().execute(
            "SELECT k.*, c.codigo, u.nombre AS autor FROM casos k JOIN verificaciones v ON v.id=k.verificacion_id "
            "JOIN centros c ON c.id=v.centro_id JOIN usuarios u ON u.id=k.creado_por ORDER BY k.creado_en DESC").fetchall()
        return render_template("casos.html", rows=rows)

    @app.route("/casos/<int:kid>", methods=["POST"])
    @role_required("coordinador")
    def caso_actualizar(kid):
        db = get_db()
        k = db.execute("SELECT * FROM casos WHERE id=?", (kid,)).fetchone() or abort(404)
        accion, ref = request.form.get("accion"), request.form.get("referencia", "").strip()
        if k["estado"] != "Borrador":
            flash("Solo se pueden actualizar casos en borrador.", "error")
        elif accion == "registrar" and not ref:
            flash("Indique la referencia del caso creado manualmente en Aranda.", "error")
        elif accion in ("registrar", "descartar"):
            estado = "Registrado en Aranda (manual)" if accion == "registrar" else "Descartado"
            db.execute("UPDATE casos SET estado=?, referencia_aranda=?, actualizado_en=? WHERE id=?",
                       (estado, ref[:50] or None, ahora().strftime(FMT), kid))
            auditar("estado", "caso", kid, estado)
            db.commit()
            flash(f"Caso actualizado: {estado}.", "ok")
        return redirect(url_for("casos"))

    @app.route("/auditoria")
    @role_required("coordinador")
    def auditoria():
        rows = get_db().execute("SELECT a.*, u.nombre FROM auditoria a LEFT JOIN usuarios u ON u.id=a.usuario_id "
                                "ORDER BY a.id DESC LIMIT 200").fetchall()
        return render_template("auditoria.html", rows=rows)

    # API para dispositivos (base para HU-07 futura)
    @app.route("/api/eventos", methods=["POST"])
    def api_eventos():
        key = app.config["API_KEY"]
        if not key:
            return jsonify(error="API deshabilitada: configure API_KEY"), 503
        if not secrets.compare_digest(request.headers.get("X-API-Key", ""), key):
            return jsonify(error="No autorizado"), 401
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="El cuerpo debe ser un objeto JSON"), 400
        tipo = data.get("tipo")
        c = get_db().execute("SELECT * FROM centros WHERE codigo=?", (str(data.get("codigo_centro", "")).upper(),)).fetchone()
        if not c or tipo not in TIPOS_EVENTO:
            return jsonify(error="codigo_centro o tipo inválido", tipos=list(TIPOS_EVENTO)), 400
        fecha = data.get("ocurrido_en")
        if fecha is not None and not isinstance(fecha, str):
            return jsonify(error="ocurrido_en debe ser una fecha en texto"), 400
        oc = parse_dt(fecha) if fecha else ahora()
        if oc is None:
            return jsonify(error="ocurrido_en debe tener formato YYYY-MM-DD HH:MM:SS"), 400
        if oc > ahora() + timedelta(minutes=1):
            return jsonify(error="La fecha de ocurrencia no puede estar en el futuro"), 400
        eid, nuevo = registrar_evento(c["id"], tipo, oc.strftime(FMT), "api", str(data.get("nota", ""))[:300])
        get_db().commit()
        return jsonify(id=eid, duplicado=not nuevo), (201 if nuevo else 200)

    @app.route("/salud")
    def salud():
        get_db().execute("SELECT 1")
        return jsonify(estado="ok", hora=ahora().strftime(FMT))

    @app.errorhandler(403)
    def prohibido(_e):
        return render_template("error.html", codigo=403, msg="Su rol no tiene permiso para esta acción."), 403

    @app.errorhandler(404)
    def no_encontrado(_e):
        return render_template("error.html", codigo=404, msg="No se encontró el recurso solicitado."), 404

    # --------------------------------------------------------- comandos CLI
    @app.cli.command("init-db")
    @click.option("--demo/--sin-demo", default=True, help="Cargar datos ficticios de demostración")
    def init_db_cmd(demo):
        """Crea las tablas, los usuarios y (opcional) datos ficticios."""
        init_db()
        db = get_db()
        for usuario, nombre, rol, env in (("coordinador", "Coordinador de Redes (demo)", "coordinador", "COORD_PASSWORD"),
                                          ("tecnico", "Técnico de Redes (demo)", "tecnico", "TECNICO_PASSWORD")):
            if db.execute("SELECT 1 FROM usuarios WHERE usuario=?", (usuario,)).fetchone():
                continue
            pwd = os.environ.get(env) or secrets.token_urlsafe(9)
            db.execute("INSERT INTO usuarios(usuario, nombre, rol, password_hash) VALUES (?,?,?,?)",
                       (usuario, nombre, rol, generate_password_hash(pwd)))
            click.echo(f"Usuario '{usuario}' creado" + ("" if os.environ.get(env) else f" con contraseña: {pwd}"))
        if demo and not db.execute("SELECT 1 FROM centros").fetchone():
            from seed import cargar_demo
            cargar_demo(db, ahora())
            click.echo("Datos ficticios de demostración cargados.")
        db.commit()
        click.echo("Base de datos lista.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
