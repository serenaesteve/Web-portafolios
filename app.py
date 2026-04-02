from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
import sqlite3, hashlib, json, re
from datetime import datetime
import requests

app = Flask(__name__)
app.secret_key = "portify_cambia_esto_en_produccion"

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3"
DB_PATH      = "portify.db"

PLANES = {
    "free":    {"nombre": "Free",    "precio": 0,  "max_portfolios": 1},
    "pro":     {"nombre": "Pro",     "precio": 9,  "max_portfolios": 5},
    "premium": {"nombre": "Premium", "precio": 19, "max_portfolios": 999},
}

# ── DB ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            email     TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            plan      TEXT DEFAULT 'free',
            creado_en TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS portfolios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id    INTEGER NOT NULL,
            titulo        TEXT,
            datos         TEXT,
            html_generado TEXT,
            creado_en     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        );
        """)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── OLLAMA ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres el asistente de Portify, una plataforma para crear portfolios web profesionales.
Tu personalidad es cálida, cercana y motivadora. Hablas como un amigo que entiende de diseño web, no como un robot.

Tu misión: hacer UNA pregunta a la vez para conocer al usuario y crear su portfolio ideal.
El usuario puede no saber nada de diseño ni tecnología — adapta tu lenguaje a lo que él entiende.

FLUJO DE CONVERSACIÓN (sigue este orden, con tus propias palabras naturales):

Paso 1 — Nombre: Pregúntale cómo se llama.

Paso 2 — A qué se dedica: Pregúntale a qué se dedica, qué estudia o qué le apasiona profesionalmente.
         (Puede ser "diseñadora", "estudio DAM", "fotógrafa freelance", "busco trabajo de programador"...)

Paso 3 — Su historia: Pídele que se describa en 2-3 frases como si se presentara a alguien nuevo.
         Dile que no tiene que ser perfecto, que ya lo pulirás tú.

Paso 4 — Lo que sabe hacer: Pregúntale qué sabe hacer, qué programas usa, qué se le da bien.
         Puede decir cosas como "Figma, Photoshop, soy buena organizando" — todo vale.

Paso 5 — Sus proyectos: Pregúntale si tiene cosas que haya hecho y quiera mostrar.
         Pueden ser proyectos del cole, trabajos freelance, apps, fotos, diseños...
         Pídele que te cuente 2 o 3 con una pequeña descripción.

Paso 6 — Experiencia: Pregúntale si tiene experiencia laboral, prácticas o formación destacada.
         Si dice que no tiene, está perfecto, lo apuntas como estudiante o sin experiencia y sigues.

Paso 7 — Contacto: Pregúntale cómo quiere que la gente le contacte.
         Email, LinkedIn, GitHub, Instagram... lo que tenga y quiera poner.

Paso 8 — Estilo visual: Aquí viene la parte divertida. Pregúntale cómo imagina su portfolio.
         Dale ejemplos concretos y visuales:
         - "Oscuro y tecnológico, como una app de videojuegos"
         - "Claro y minimalista, como una revista de diseño"
         - "Colorido y creativo, con mucha personalidad"
         Interpreta su respuesta y elige entre: moderno, minimalista o creativo.
         Si elige oscuro → tema: oscuro. Si elige claro → tema: claro.

Paso 9 — Color: Pregúntale qué color le representa o le gusta para su web.
         Ofrécele estas opciones de forma visual y simpática:
         🌸 Rosa coral — elegante y moderno
         🌹 Rosa frambuesa — intenso y sofisticado
         🌿 Morado suave — creativo y diferente
         🌊 Azul petróleo — serio y profesional
         🍑 Melocotón — cálido y acogedor

Cuando tengas respuesta de los 9 pasos, genera el JSON. SOLO el JSON, sin texto antes ni después:
{"listo":true,"datos":{"nombre":"","rol":"","descripcion":"","habilidades":[],"proyectos":[{"titulo":"","descripcion":"","tecnologias":""}],"experiencia":[{"titulo":"","descripcion":""}],"email":"","redes":{"linkedin":"","github":""},"estilo":"moderno","tema":"claro","color":"#F18A8E"}}

Mapeo de colores:
- Rosa coral → #F18A8E
- Rosa frambuesa → #E06A7C
- Morado suave → #6B5A7A
- Azul petróleo → #3E627F
- Melocotón → #F2B38C

REGLAS ESTRICTAS:
- SIEMPRE en español
- UNA pregunta por mensaje, nunca dos
- Si el usuario no tiene algo, acepta y sigue
- Nunca menciones "JSON", "campos", "base de datos" ni tecnicismos al usuario
- No generes el JSON hasta tener los 9 pasos completos
- Sé natural, usa emojis con moderación, haz que sea una experiencia agradable"""

def chat_ollama(messages):
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=120
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama no está corriendo. Abre una terminal y ejecuta: `ollama serve`"
    except requests.exceptions.Timeout:
        return "⚠️ Ollama tardó demasiado en responder. Inténtalo de nuevo."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

def parse_json_ollama(texto):
    try:
        m = re.search(r'\{.*?"listo"\s*:\s*true.*?\}', texto, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return None

# ── GENERADOR HTML DEL PORTFOLIO ─────────────────────────────────────────
def generar_html(datos):
    nombre    = datos.get("nombre", "Tu Nombre")
    rol       = datos.get("rol", "Profesional")
    desc      = datos.get("descripcion", "")
    skills    = datos.get("habilidades", [])
    proyectos = datos.get("proyectos", [])
    exp       = datos.get("experiencia", [])
    email     = datos.get("email", "")
    redes     = datos.get("redes", {}) or {}
    estilo    = datos.get("estilo", "moderno")
    tema      = datos.get("tema", "claro")
    color     = datos.get("color", "#F18A8E")
    oscuro    = tema == "oscuro"

    bg      = "#0d0d18" if oscuro else "#fafafa"
    txt     = "#f0f4f8" if oscuro else "#111827"
    muted   = "#8892a4" if oscuro else "#6b7280"
    card_bg = "rgba(255,255,255,0.05)" if oscuro else "rgba(255,255,255,0.95)"
    card_br = "rgba(255,255,255,0.09)" if oscuro else "rgba(0,0,0,0.07)"
    nav_bg  = "rgba(13,13,24,0.80)" if oscuro else "rgba(250,250,250,0.80)"

    skills_html   = "".join(f'<span class="pill">{s}</span>' for s in skills)
    proyectos_html = ""
    for p in proyectos:
        proyectos_html += f"""<article class="pcard">
          <div class="pthumb"></div>
          <div class="pinfo">
            <h4>{p.get('titulo','')}</h4>
            <p>{p.get('descripcion','')}</p>
            <span class="ptag">{p.get('tecnologias','')}</span>
          </div>
        </article>"""

    exp_html = ""
    for e in exp:
        if isinstance(e, dict):
            exp_html += f'<div class="titem"><div class="tdot"></div><div><strong>{e.get("titulo","")}</strong><p>{e.get("descripcion","")}</p></div></div>'
        elif isinstance(e, str) and e.strip():
            exp_html += f'<div class="titem"><div class="tdot"></div><div><p>{e}</p></div></div>'

    linkedin = redes.get("linkedin","") or ""
    github   = redes.get("github","") or ""
    ini      = nombre[0].upper() if nombre else "P"

    btns = f'<a href="mailto:{email}" class="pbtn pp">✉ Contactar</a>' if email else ""
    if linkedin and linkedin not in ["#","ninguna","none",""]:
        btns += f'<a href="{linkedin}" class="pbtn ps" target="_blank">LinkedIn</a>'
    if github and github not in ["#","ninguna","none",""]:
        btns += f'<a href="{github}" class="pbtn ps" target="_blank">GitHub</a>'

    exp_section = f'<section id="exp"><div class="narrow"><h2>Experiencia</h2><div class="tl">{exp_html}</div></div></section>' if exp_html else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nombre} · Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--c:{color};--bg:{bg};--t:{txt};--m:{muted};--cb:{card_bg};--cbr:{card_br};--nav:{nav_bg}}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--t);line-height:1.7;min-height:100vh}}
a{{color:var(--c);text-decoration:none}}
.wrap{{width:min(1080px,calc(100% - 48px));margin:0 auto}}
.narrow{{width:min(760px,calc(100% - 48px));margin:0 auto}}
nav{{padding:16px 0;border-bottom:1px solid var(--cbr);position:sticky;top:0;background:var(--nav);backdrop-filter:blur(20px);z-index:100}}
.ni{{display:flex;align-items:center;justify-content:space-between}}
.nlogo{{font-family:'Syne',sans-serif;font-weight:800;font-size:1.1rem;letter-spacing:-.03em;color:var(--t)}}
.nl{{display:flex;gap:28px}}
.nl a{{color:var(--m);font-size:.88rem;font-weight:500;transition:.15s;letter-spacing:.02em;text-transform:uppercase}}
.nl a:hover{{color:var(--t)}}
.hero{{padding:100px 0 80px;position:relative;overflow:hidden}}
.hero::before{{content:'';position:absolute;top:-200px;right:-200px;width:600px;height:600px;border-radius:50%;background:radial-gradient(circle,{color}22 0%,transparent 70%);pointer-events:none}}
.hg{{display:grid;grid-template-columns:1fr 380px;gap:60px;align-items:center}}
.tag{{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:999px;background:{"rgba(255,255,255,0.07)" if oscuro else "rgba(0,0,0,0.05)"};border:1px solid var(--cbr);font-size:.78rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--m);margin-bottom:24px}}
.tag span{{width:6px;height:6px;border-radius:50%;background:var(--c);display:inline-block}}
h1{{font-family:'Syne',sans-serif;font-size:clamp(3rem,5.5vw,5.2rem);line-height:.92;letter-spacing:-.05em;margin-bottom:14px;font-weight:800}}
h1 em{{font-style:normal;color:var(--c)}}
.rol{{font-size:1.1rem;font-weight:500;color:var(--m);margin-bottom:20px;letter-spacing:.01em}}
.desc{{color:var(--m);font-size:1rem;max-width:520px;line-height:1.85;font-weight:300}}
.hbtns{{display:flex;gap:12px;margin-top:32px;flex-wrap:wrap}}
.pbtn{{padding:12px 24px;border-radius:10px;font-weight:600;font-size:.92rem;transition:.2s;display:inline-flex;align-items:center;gap:8px;font-family:'DM Sans',sans-serif}}
.pp{{background:var(--c);color:#fff;border:none}}
.pp:hover{{filter:brightness(.9);transform:translateY(-1px)}}
.ps{{background:var(--cb);color:var(--t);border:1px solid var(--cbr)}}
.ps:hover{{border-color:var(--c);color:var(--c)}}
.acard{{background:var(--cb);border:1px solid var(--cbr);border-radius:20px;padding:36px;position:relative;overflow:hidden}}
.acard::before{{content:'';position:absolute;top:-60px;right:-60px;width:180px;height:180px;border-radius:50%;background:radial-gradient(circle,{color}18 0%,transparent 70%)}}
.av{{width:72px;height:72px;border-radius:16px;background:var(--c);color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;margin-bottom:20px}}
.acard h3{{font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:700;letter-spacing:-.03em;margin-bottom:4px}}
.acard .arole{{color:var(--c);font-size:.9rem;font-weight:600;margin-bottom:18px}}
.atags{{display:flex;flex-wrap:wrap;gap:8px}}
.atag{{padding:6px 12px;border-radius:8px;background:{"rgba(255,255,255,0.06)" if oscuro else "rgba(0,0,0,0.04)"};font-size:.8rem;font-weight:500;color:var(--m)}}
section{{padding:72px 0}}
section h2{{font-family:'Syne',sans-serif;font-size:1.9rem;font-weight:700;letter-spacing:-.04em;margin-bottom:32px}}
.sline{{display:flex;align-items:center;gap:14px;margin-bottom:32px}}
.sline h2{{margin:0}}
.sline::after{{content:'';flex:1;height:1px;background:var(--cbr)}}
.pill{{padding:9px 16px;border-radius:8px;background:var(--cb);border:1px solid var(--cbr);font-size:.88rem;font-weight:500;display:inline-flex;color:var(--t)}}
.skills{{display:flex;flex-wrap:wrap;gap:10px}}
.pg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}}
.pcard{{background:var(--cb);border:1px solid var(--cbr);border-radius:16px;overflow:hidden;transition:.2s}}
.pcard:hover{{border-color:var(--c);transform:translateY(-2px)}}
.pthumb{{height:160px;background:linear-gradient(135deg,{color}60,{color}20);position:relative}}
.pthumb::after{{content:'↗';position:absolute;top:12px;right:14px;font-size:1.1rem;color:{color};opacity:.6}}
.pinfo{{padding:20px}}
.pinfo h4{{font-family:'Syne',sans-serif;font-size:1rem;font-weight:700;margin-bottom:8px;letter-spacing:-.02em}}
.pinfo p{{color:var(--m);font-size:.88rem;margin-bottom:12px;line-height:1.7}}
.ptag{{display:inline-flex;padding:4px 10px;border-radius:6px;background:{"rgba(255,255,255,0.06)" if oscuro else "rgba(0,0,0,0.04)"};font-size:.78rem;font-weight:600;color:var(--m);letter-spacing:.02em}}
.tl{{display:flex;flex-direction:column;gap:0}}
.titem{{display:grid;grid-template-columns:20px 1fr;gap:20px;padding-bottom:28px;position:relative}}
.titem:last-child{{padding-bottom:0}}
.tdot{{width:10px;height:10px;border-radius:50%;background:var(--c);margin-top:8px;position:relative;z-index:1}}
.titem::before{{content:'';position:absolute;left:4px;top:18px;bottom:0;width:2px;background:var(--cbr)}}
.titem:last-child::before{{display:none}}
.titem strong{{display:block;font-weight:600;font-size:.97rem;margin-bottom:4px}}
.titem p{{color:var(--m);font-size:.9rem;line-height:1.7}}
.cbox{{background:var(--cb);border:1px solid var(--cbr);border-radius:20px;padding:48px;text-align:center;position:relative;overflow:hidden}}
.cbox::before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 50% 0%,{color}12 0%,transparent 60%)}}
.cbox h2{{font-family:'Syne',sans-serif;font-size:2rem;margin-bottom:12px;position:relative}}
.cbox p{{color:var(--m);margin-bottom:28px;position:relative;font-size:1rem}}
.cbtns{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;position:relative}}
footer{{padding:32px 0;border-top:1px solid var(--cbr);text-align:center;color:var(--m);font-size:.82rem;letter-spacing:.02em}}
@media(max-width:860px){{.hg{{grid-template-columns:1fr}}.nl{{display:none}}}}
</style>
</head>
<body>
<nav><div class="wrap ni">
  <span class="nlogo">{nombre.split()[0] if nombre else 'Portfolio'}</span>
  <div class="nl">
    <a href="#skills">Habilidades</a>
    <a href="#proyectos">Proyectos</a>
    {"<a href='#exp'>Experiencia</a>" if exp_html else ""}
    <a href="#contacto">Contacto</a>
  </div>
</div></nav>

<section class="hero">
  <div class="wrap hg">
    <div>
      <div class="tag"><span></span>{estilo.capitalize()} · {tema.capitalize()}</div>
      <h1>{nombre.split()[0] if ' ' in nombre else nombre}<br><em>{nombre.split()[-1] if ' ' in nombre else ''}</em></h1>
      <p class="rol">{rol}</p>
      <p class="desc">{desc}</p>
      <div class="hbtns">{btns if btns else '<a href="#proyectos" class="pbtn pp">Ver proyectos</a>'}</div>
    </div>
    <div class="acard">
      <div class="av">{ini}</div>
      <h3>{nombre}</h3>
      <p class="arole">{rol}</p>
      <div class="atags">{''.join(f'<span class="atag">{s}</span>' for s in skills[:5])}</div>
    </div>
  </div>
</section>

<section id="skills"><div class="narrow">
  <div class="sline"><h2>Habilidades</h2></div>
  <div class="skills">{skills_html}</div>
</div></section>

<section id="proyectos"><div class="wrap">
  <div class="sline"><h2>Proyectos</h2></div>
  <div class="pg">{proyectos_html}</div>
</div></section>

{exp_section}

<section id="contacto"><div class="narrow">
  <div class="cbox">
    <h2>¿Hablamos?</h2>
    <p>Abierto a nuevas oportunidades y colaboraciones.</p>
    <div class="cbtns">{btns if btns else '<span style="color:var(--m)">Sin datos de contacto</span>'}</div>
  </div>
</div></section>

<footer><div class="wrap"><p>Creado con Portify · {datetime.now().year}</p></div></footer>
</body></html>"""

# ── RUTAS ────────────────────────────────────────────────────────────────
@app.route("/")
def landing(): return render_template("landing.html")

@app.route("/registro", methods=["GET","POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre","").strip()
        email  = request.form.get("email","").strip().lower()
        pw     = request.form.get("password","")
        if not nombre or not email or not pw:
            return render_template("registro.html", error="Rellena todos los campos.")
        try:
            with get_db() as db:
                db.execute("INSERT INTO usuarios (nombre,email,password) VALUES (?,?,?)",
                           (nombre, email, hash_pw(pw)))
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("registro.html", error="Ese email ya está registrado.")
    return render_template("registro.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw    = request.form.get("password","")
        with get_db() as db:
            u = db.execute("SELECT * FROM usuarios WHERE email=? AND password=?",
                           (email, hash_pw(pw))).fetchone()
        if u:
            session.update({"user_id": u["id"], "user_nombre": u["nombre"], "user_plan": u["plan"]})
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Email o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("landing"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        portfolios = db.execute("SELECT * FROM portfolios WHERE usuario_id=? ORDER BY creado_en DESC",
                                (session["user_id"],)).fetchall()
        user = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
    plan = PLANES.get(user["plan"], PLANES["free"])
    return render_template("dashboard.html", portfolios=portfolios, user=user, plan=plan)

@app.route("/chat")
def chat():
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        user  = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
        count = db.execute("SELECT COUNT(*) as c FROM portfolios WHERE usuario_id=?",
                           (session["user_id"],)).fetchone()["c"]
    plan = PLANES.get(user["plan"], PLANES["free"])
    if count >= plan["max_portfolios"]: return redirect(url_for("planes"))
    session["chat_history"] = []
    return render_template("chat.html", user=user)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "user_id" not in session: return jsonify({"error": "No autenticado"}), 401
    data    = request.get_json()
    msg     = data.get("mensaje","").strip()
    history = session.get("chat_history", [])

    if not history:
        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "assistant", "content": "¡Hola! 👋 Estoy aquí para ayudarte a crear tu portfolio. Cuéntame, ¿cómo te llamas?"}
        ]

    history.append({"role": "user", "content": msg})
    respuesta = chat_ollama(history)
    history.append({"role": "assistant", "content": respuesta})
    session["chat_history"] = history

    parsed = parse_json_ollama(respuesta)
    if parsed and parsed.get("listo"):
        return jsonify({"respuesta": "¡Perfecto! Ya tengo todo lo que necesito. Tu portfolio está listo para generarse ✨", "listo": True, "datos": parsed["datos"]})

    return jsonify({"respuesta": respuesta, "listo": False})

@app.route("/generar-portfolio", methods=["POST"])
def generar_portfolio():
    if "user_id" not in session: return jsonify({"error": "No autenticado"}), 401
    datos  = request.get_json().get("datos", {})
    html   = generar_html(datos)
    titulo = f"Portfolio de {datos.get('nombre','Usuario')}"
    with get_db() as db:
        cur = db.execute("INSERT INTO portfolios (usuario_id,titulo,datos,html_generado) VALUES (?,?,?,?)",
                         (session["user_id"], titulo, json.dumps(datos), html))
        pid = cur.lastrowid
    return jsonify({"ok": True, "portfolio_id": pid})

@app.route("/portfolio/<int:pid>")
def ver_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
    if not p: return "No encontrado", 404
    return p["html_generado"]

@app.route("/portfolio/<int:pid>/descargar")
def descargar_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
    if not p: return "No encontrado", 404
    return Response(p["html_generado"], mimetype="text/html",
                    headers={"Content-Disposition": f"attachment; filename=portfolio_{pid}.html"})

@app.route("/portfolio/<int:pid>/eliminar", methods=["POST"])
def eliminar_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        db.execute("DELETE FROM portfolios WHERE id=? AND usuario_id=?", (pid, session["user_id"]))
    return redirect(url_for("dashboard"))

@app.route("/planes")
def planes():
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        user = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
    return render_template("planes.html", user=user, planes=PLANES)

@app.route("/activar-plan/<plan_id>")
def activar_plan(plan_id):
    if "user_id" not in session or plan_id not in PLANES: return redirect(url_for("planes"))
    with get_db() as db:
        db.execute("UPDATE usuarios SET plan=? WHERE id=?", (plan_id, session["user_id"]))
    session["user_plan"] = plan_id
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
