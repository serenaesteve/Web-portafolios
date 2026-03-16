from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
import sqlite3, hashlib, os, json, re
from datetime import datetime
import requests

app = Flask(__name__)
app.secret_key = "portify_cambia_esto_en_produccion"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3"
DB_PATH = "portify.db"

PLANES = {
    "free":    {"nombre": "Free",    "precio": 0,  "max_portfolios": 1},
    "pro":     {"nombre": "Pro",     "precio": 9,  "max_portfolios": 5},
    "premium": {"nombre": "Premium", "precio": 19, "max_portfolios": 999},
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            creado_en TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            titulo TEXT,
            datos TEXT,
            html_generado TEXT,
            creado_en TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        );
        """)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

SYSTEM_PROMPT = """Eres un asistente amigable de Portify. Tu trabajo es hacer preguntas UNA A UNA para crear el portfolio del usuario.

Orden de preguntas:
1. Nombre completo
2. Rol / profesión
3. Descripción personal (2-3 frases)
4. Habilidades principales (4-6)
5. Proyectos destacados (2-3): título, descripción, tecnologías
6. Experiencia laboral o académica
7. Email de contacto y redes (LinkedIn, GitHub)
8. Estilo visual: moderno, minimalista o creativo
9. Tema: claro u oscuro
10. Color favorito (opciones: coral #F18A8E, rosa #E06A7C, morado #6B5A7A, azul #3E627F)

Cuando tengas TODO, responde SOLO con este JSON (sin texto extra):
{"listo":true,"datos":{"nombre":"...","rol":"...","descripcion":"...","habilidades":["..."],"proyectos":[{"titulo":"...","descripcion":"...","tecnologias":"..."}],"experiencia":[{"titulo":"...","descripcion":"..."}],"email":"...","redes":{"linkedin":"...","github":"..."},"estilo":"moderno","tema":"claro","color":"#F18A8E"}}

Habla siempre en español, sé amigable y usa emojis."""

def chat_ollama(messages):
    try:
        r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "messages": messages, "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama no está corriendo. Ejecuta: `ollama serve` en tu terminal."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

def parse_json_ollama(texto):
    try:
        m = re.search(r'\{.*"listo"\s*:\s*true.*\}', texto, re.DOTALL)
        if m:
            return json.loads(m.group())
    except:
        pass
    return None

def generar_html(datos):
    nombre    = datos.get("nombre", "Tu Nombre")
    rol       = datos.get("rol", "Profesional")
    desc      = datos.get("descripcion", "")
    skills    = datos.get("habilidades", [])
    proyectos = datos.get("proyectos", [])
    exp       = datos.get("experiencia", [])
    email     = datos.get("email", "")
    redes     = datos.get("redes", {})
    estilo    = datos.get("estilo", "moderno")
    tema      = datos.get("tema", "claro")
    color     = datos.get("color", "#f18a8e")
    oscuro    = tema == "oscuro"

    bg       = "#0f0f1a" if oscuro else "#f8fafc"
    bg2      = "#1a1a2e" if oscuro else "#ffffff"
    txt      = "#f1f5f9" if oscuro else "#1f2937"
    muted    = "#94a3b8" if oscuro else "#6b7280"
    card_bg  = "rgba(255,255,255,0.05)" if oscuro else "rgba(255,255,255,0.9)"
    card_br  = "rgba(255,255,255,0.08)" if oscuro else "rgba(234,222,222,0.9)"

    skills_html = "".join(f'<span class="pill">{s}</span>' for s in skills)
    proyectos_html = "".join(f'''
    <article class="card">
      <div class="thumb"></div>
      <h4>{p.get("titulo","")}</h4>
      <p>{p.get("descripcion","")}</p>
      <span class="pill small">{p.get("tecnologias","")}</span>
    </article>''' for p in proyectos)

    exp_html = ""
    for e in exp:
        if isinstance(e, dict):
            exp_html += f'<div class="tl-item"><div class="dot"></div><div><strong>{e.get("titulo","")}</strong><p>{e.get("descripcion","")}</p></div></div>'
        elif isinstance(e, str):
            exp_html += f'<div class="tl-item"><div class="dot"></div><div><p>{e}</p></div></div>'

    linkedin = redes.get("linkedin", "") if redes else ""
    github   = redes.get("github", "") if redes else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nombre} | Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--c:{color};--bg:{bg};--bg2:{bg2};--t:{txt};--m:{muted};--cb:{card_bg};--cbr:{card_br};--r:20px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--t);line-height:1.7}}
a{{color:var(--c);text-decoration:none}}
.wrap{{width:min(1100px,calc(100% - 40px));margin:0 auto}}
.narrow{{width:min(820px,calc(100% - 40px));margin:0 auto}}
nav{{padding:18px 0;border-bottom:1px solid var(--cbr);position:sticky;top:0;background:var(--bg);z-index:10}}
.nav-i{{display:flex;align-items:center;justify-content:space-between}}
.logo{{font-weight:800;font-size:1.3rem;letter-spacing:-.04em;color:var(--t)}}
.nav-links{{display:flex;gap:24px}}
.nav-links a{{color:var(--m);font-weight:500;transition:.2s}}
.nav-links a:hover{{color:var(--t)}}
.hero{{padding:80px 0 60px}}
.hero-g{{display:grid;grid-template-columns:1.1fr .9fr;gap:40px;align-items:center}}
.badge{{display:inline-flex;padding:8px 16px;border-radius:999px;background:var(--c);color:#fff;font-weight:600;font-size:.85rem;margin-bottom:20px}}
h1{{font-size:clamp(2.8rem,6vw,5rem);line-height:.95;letter-spacing:-.06em;margin-bottom:12px}}
.rol{{color:var(--c);font-size:1.3rem;font-weight:700;margin-bottom:18px}}
.desc{{color:var(--m);font-size:1.05rem;max-width:560px}}
.btns{{display:flex;gap:14px;margin-top:28px;flex-wrap:wrap}}
.btn{{padding:14px 26px;border-radius:999px;font-weight:700;border:none;cursor:pointer;font-size:1rem}}
.btn-p{{background:var(--c);color:#fff}}
.btn-s{{background:var(--cb);color:var(--t);border:1px solid var(--cbr)}}
.avatar-box{{background:var(--cb);border:1px solid var(--cbr);border-radius:var(--r);padding:32px;text-align:center}}
.av{{width:80px;height:80px;border-radius:50%;background:var(--c);color:#fff;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:800;margin:0 auto 16px}}
.avatar-box h3{{font-size:1.5rem;margin-bottom:6px}}
.avatar-box p{{color:var(--m)}}
section{{padding:60px 0}}
section h2{{font-size:2rem;font-weight:800;letter-spacing:-.04em;margin-bottom:28px}}
.pill{{padding:10px 18px;border-radius:999px;background:var(--cb);border:1px solid var(--cbr);font-weight:600;font-size:.95rem;display:inline-flex}}
.pill.small{{font-size:.82rem;padding:6px 12px;color:var(--m)}}
.skills{{display:flex;flex-wrap:wrap;gap:12px}}
.grid-3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:22px}}
.card{{background:var(--cb);border:1px solid var(--cbr);border-radius:var(--r);padding:22px}}
.thumb{{height:150px;border-radius:14px;background:var(--c);margin-bottom:16px;opacity:.75}}
.card h4{{font-size:1.1rem;margin-bottom:10px}}
.card p{{color:var(--m);margin-bottom:14px;font-size:.95rem}}
.tl{{display:grid;gap:22px;padding-left:20px;position:relative}}
.tl::before{{content:'';position:absolute;left:6px;top:0;bottom:0;width:2px;background:var(--c);opacity:.3}}
.tl-item{{display:grid;grid-template-columns:24px 1fr;gap:14px}}
.dot{{width:14px;height:14px;border-radius:50%;background:var(--c);margin-top:5px}}
.tl-item strong{{display:block;margin-bottom:6px}}
.tl-item p{{color:var(--m)}}
.contact-card{{background:var(--cb);border:1px solid var(--cbr);border-radius:var(--r);padding:40px;text-align:center}}
.contact-card p{{color:var(--m);margin-bottom:24px}}
.contact-links{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}}
footer{{padding:28px 0;border-top:1px solid var(--cbr);text-align:center;color:var(--m);font-size:.9rem}}
@media(max-width:900px){{.hero-g{{grid-template-columns:1fr}}.nav-links{{display:none}}}}
</style>
</head>
<body>
<nav><div class="wrap nav-i">
  <span class="logo">{nombre.split()[0] if nombre else 'Portfolio'}</span>
  <div class="nav-links">
    <a href="#habilidades">Habilidades</a>
    <a href="#proyectos">Proyectos</a>
    {"<a href='#experiencia'>Experiencia</a>" if exp_html else ""}
    <a href="#contacto">Contacto</a>
  </div>
</div></nav>
<main>
<section class="hero"><div class="wrap hero-g">
  <div>
    <span class="badge">{estilo.capitalize()} · {tema.capitalize()}</span>
    <h1>{nombre}</h1>
    <p class="rol">{rol}</p>
    <p class="desc">{desc}</p>
    <div class="btns">
      <a href="#proyectos" class="btn btn-p">Ver proyectos</a>
      <a href="#contacto" class="btn btn-s">Contacto</a>
    </div>
  </div>
  <div class="avatar-box">
    <div class="av">{nombre[0].upper() if nombre else 'P'}</div>
    <h3>{nombre}</h3><p>{rol}</p>
    <div class="skills" style="margin-top:16px;justify-content:center">
      {"".join(f'<span class="pill">{s}</span>' for s in skills[:3])}
    </div>
  </div>
</div></section>

<section id="habilidades"><div class="narrow">
  <h2>Habilidades</h2>
  <div class="skills">{skills_html}</div>
</div></section>

<section id="proyectos"><div class="wrap">
  <h2>Proyectos</h2>
  <div class="grid-3">{proyectos_html}</div>
</div></section>

{"<section id='experiencia'><div class='narrow'><h2>Experiencia</h2><div class='tl'>" + exp_html + "</div></div></section>" if exp_html else ""}

<section id="contacto"><div class="narrow">
  <div class="contact-card">
    <h2>¿Hablamos?</h2>
    <p>¿Tienes un proyecto en mente o quieres colaborar?</p>
    <div class="contact-links">
      {"<a href='mailto:" + email + "' class='btn btn-p'>✉ Email</a>" if email else ""}
      {"<a href='" + linkedin + "' class='btn btn-s' target='_blank'>LinkedIn</a>" if linkedin and linkedin not in ['#',''] else ""}
      {"<a href='" + github + "' class='btn btn-s' target='_blank'>GitHub</a>" if github and github not in ['#',''] else ""}
    </div>
  </div>
</div></section>
</main>
<footer><div class="wrap"><p>Creado con <strong>Portify</strong> · {datetime.now().year}</p></div></footer>
</body></html>"""

# ── RUTAS ──
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/registro", methods=["GET","POST"])
def registro():
    if request.method == "POST":
        nombre   = request.form.get("nombre","").strip()
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not nombre or not email or not password:
            return render_template("registro.html", error="Rellena todos los campos.")
        try:
            with get_db() as db:
                db.execute("INSERT INTO usuarios (nombre,email,password) VALUES (?,?,?)",
                           (nombre, email, hash_pw(password)))
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("registro.html", error="Ese email ya está registrado.")
    return render_template("registro.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        with get_db() as db:
            user = db.execute("SELECT * FROM usuarios WHERE email=? AND password=?",
                              (email, hash_pw(password))).fetchone()
        if user:
            session["user_id"]     = user["id"]
            session["user_nombre"] = user["nombre"]
            session["user_plan"]   = user["plan"]
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Email o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as db:
        portfolios = db.execute("SELECT * FROM portfolios WHERE usuario_id=? ORDER BY creado_en DESC",
                                (session["user_id"],)).fetchall()
        user = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
    plan = PLANES.get(user["plan"], PLANES["free"])
    return render_template("dashboard.html", portfolios=portfolios, user=user, plan=plan)

@app.route("/chat")
def chat():
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as db:
        user  = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
        count = db.execute("SELECT COUNT(*) as c FROM portfolios WHERE usuario_id=?",
                           (session["user_id"],)).fetchone()["c"]
    plan = PLANES.get(user["plan"], PLANES["free"])
    if count >= plan["max_portfolios"]:
        return redirect(url_for("planes"))
    session["chat_history"] = []
    return render_template("chat.html", user=user)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    data     = request.get_json()
    user_msg = data.get("mensaje", "").strip()
    history  = session.get("chat_history", [])

    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})
        history.append({"role": "assistant",
                        "content": "¡Hola! 👋 Soy tu asistente de Portify. Voy a ayudarte a crear tu portfolio haciéndote unas preguntas.\n\n¿Empezamos? 😊 ¿Cuál es tu **nombre completo**?"})

    history.append({"role": "user", "content": user_msg})
    respuesta = chat_ollama(history)
    history.append({"role": "assistant", "content": respuesta})
    session["chat_history"] = history

    parsed = parse_json_ollama(respuesta)
    if parsed and parsed.get("listo"):
        return jsonify({"respuesta": "¡Perfecto! Ya tengo toda la información. Generando tu portfolio... 🎨", "listo": True, "datos": parsed["datos"]})

    return jsonify({"respuesta": respuesta, "listo": False})

@app.route("/generar-portfolio", methods=["POST"])
def generar_portfolio():
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    datos = request.get_json().get("datos", {})
    html  = generar_html(datos)
    titulo = f"Portfolio de {datos.get('nombre','Usuario')}"
    with get_db() as db:
        cur = db.execute("INSERT INTO portfolios (usuario_id,titulo,datos,html_generado) VALUES (?,?,?,?)",
                         (session["user_id"], titulo, json.dumps(datos), html))
        pid = cur.lastrowid
    return jsonify({"ok": True, "portfolio_id": pid})

@app.route("/portfolio/<int:pid>")
def ver_portfolio(pid):
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
    if not p:
        return "Portfolio no encontrado", 404
    return p["html_generado"]

@app.route("/portfolio/<int:pid>/descargar")
def descargar_portfolio(pid):
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
    if not p:
        return "No encontrado", 404
    return Response(p["html_generado"], mimetype="text/html",
                    headers={"Content-Disposition": f"attachment; filename=portfolio_{pid}.html"})

@app.route("/portfolio/<int:pid>/eliminar", methods=["POST"])
def eliminar_portfolio(pid):
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as db:
        db.execute("DELETE FROM portfolios WHERE id=? AND usuario_id=?", (pid, session["user_id"]))
    return redirect(url_for("dashboard"))

@app.route("/planes")
def planes():
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as db:
        user = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
    return render_template("planes.html", user=user, planes=PLANES)

@app.route("/activar-plan/<plan_id>")
def activar_plan(plan_id):
    if "user_id" not in session or plan_id not in PLANES:
        return redirect(url_for("planes"))
    with get_db() as db:
        db.execute("UPDATE usuarios SET plan=? WHERE id=?", (plan_id, session["user_id"]))
    session["user_plan"] = plan_id
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
