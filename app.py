from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, stream_with_context
from markupsafe import Markup
import sqlite3, hashlib, json, re, uuid, os, base64, logging, io, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
import qrcode
from flask_session import Session
from agent_portfolio import PortfolioAgent, generar_html_universal, PLANTILLAS_DISPONIBLES
from markupsafe import escape

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-cambiar-en-produccion-' + uuid.uuid4().hex)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# ── SERVER-SIDE SESSIONS (sin límite de 4 KB) ─────────────────────────────
_SESSION_DIR = os.path.join(os.path.dirname(__file__), '.flask_sessions')
os.makedirs(_SESSION_DIR, exist_ok=True)
app.config['SESSION_TYPE']          = 'filesystem'
app.config['SESSION_FILE_DIR']      = _SESSION_DIR
app.config['SESSION_PERMANENT']     = False
app.config['SESSION_USE_SIGNER']    = True
app.config['SESSION_FILE_THRESHOLD'] = 500
Session(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS Configuration - Permitir requests desde localhost y mismo origen
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = os.environ.get('CORS_ORIGIN', 'http://localhost:5000')
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# Middleware para subdomínios dinámicos - Proxy para portafolios
DOMAIN_BASE  = os.environ.get('DOMAIN_BASE',  'portify.es')  # ej: portify.es
ADMIN_EMAIL  = os.environ.get('ADMIN_EMAIL', '')

@app.before_request
def handle_subdomain_proxy():
    """
    Intercepta requests a subdomínios como juan.portify.com
    y las redirige al portafolio específico del usuario
    """
    host = request.host.split(':')[0]  # Obtener solo el hostname sin puerto
    
    # Si no es localhost y no es el dominio base, probablemente es un subdominio
    if host != 'localhost' and host != DOMAIN_BASE.split(':')[0]:
        # Extraer el subdominio
        parts = host.split('.')
        if len(parts) > 1:
            subdomain = parts[0]  # ej: 'juan' de 'juan.portify.com'
            
            # Guardar el subdominio en g (contexto global de la request)
            from flask import g
            g.subdomain_portfolio = subdomain
            g.is_portfolio_view = True

OLLAMA_URL        = "http://localhost:11434/api/chat"
OLLAMA_MODEL      = "llama3.2:latest"
OLLAMA_VISION_MODEL = "qwen2.5vl:latest"   # modelo multimodal para visión
DB_PATH      = "portify.db"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── EMAIL ─────────────────────────────────────────────────────────────────────
# Configura via variables de entorno o edita aquí directamente.
SMTP_HOST     = os.environ.get("SMTP_HOST", "")          # ej: smtp.gmail.com
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")          # tu@gmail.com
SMTP_PASS     = os.environ.get("SMTP_PASS", "")          # contraseña o app password
SMTP_FROM     = os.environ.get("SMTP_FROM", SMTP_USER)   # remitente
ADMIN_EMAIL   = os.environ.get("ADMIN_EMAIL", "")        # email del administrador
ADMIN_PASSWORD= os.environ.get("ADMIN_PASSWORD", "portify-admin-2024")  # para /admin

def send_email(to: str, subject: str, body_html: str) -> bool:
    """Envía un email. Retorna True si tuvo éxito, False si no hay config SMTP."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        logger.info(f"[Email] Sin config SMTP — no se envió a {to}: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM or SMTP_USER
        msg["To"]      = to
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM or SMTP_USER, [to], msg.as_string())
        logger.info(f"[Email] Enviado a {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"[Email] Error enviando a {to}: {e}")
        return False

# ── PAGOS ─────────────────────────────────────────────────────────────────────
# Para activar Stripe: añade STRIPE_SECRET_KEY y STRIPE_WEBHOOK_SECRET al entorno.
# La lógica de pago real está marcada con "# [STRIPE]" en el código.
STRIPE_SECRET_KEY    = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET= os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_IDS     = {
    "pro":     os.environ.get("STRIPE_PRICE_PRO", ""),
    "premium": os.environ.get("STRIPE_PRICE_PREMIUM", ""),
}
# Tarjeta de prueba que simula rechazo (igual que Stripe test card)
_CARD_DECLINE_TEST = "4000000000000002"

PLANES = {
    "free":    {"nombre":"Free",    "precio":0,  "max_portfolios":1},
    "pro":     {"nombre":"Pro",     "precio":9,  "max_portfolios":5},
    "premium": {"nombre":"Premium", "precio":19, "max_portfolios":999},
}

ANIMACIONES = {
    "fade":       {"nombre":"Fade In",       "desc":"Aparece suavemente", "css":"fadeIn"},
    "slide-up":   {"nombre":"Slide Up",      "desc":"Sube desde abajo",   "css":"slideUp"},
    "slide-left": {"nombre":"Slide Left",    "desc":"Entra desde la derecha","css":"slideLeft"},
    "zoom":       {"nombre":"Zoom In",       "desc":"Crece desde el centro","css":"zoomIn"},
    "float":      {"nombre":"Float",         "desc":"Flota suavemente",   "css":"float"},
    "typewriter": {"nombre":"Typewriter",    "desc":"Texto aparece letra a letra","css":"typewriter"},
}

ANIM_POR_PLANTILLA = {
    "oscuro":      "slide-up",
    "minimalista": "fade",
    "creativo":    "zoom",
    "editorial":   "slide-left",
    "organico":    "float",
    "glass":       "zoom",
    "neo":         "slide-up",
    "terminal":    "fade",
    "luxury":      "fade",
    "retro":       "slide-up",
    "nordic":      "slide-left",
    "pastel":      "float",
    "neon":        "zoom",
    "magazine":    "slide-left",
    "gradient":    "zoom",
}

# ── DB ───────────────────────────────────────────────────────────────────
# Rate limiting simple sin dependencias
from collections import defaultdict
from time import time

request_history = defaultdict(list)

def check_rate_limit(user_id, max_requests=20, window_seconds=60):
    """Rate limiting simple por usuario: máx 20 requests por minuto."""
    now = time()
    # Limpiar requests viejos
    request_history[user_id] = [ts for ts in request_history[user_id] if now - ts < window_seconds]
    # Verificar límite
    if len(request_history[user_id]) >= max_requests:
        logger.warning(f"Rate limit excedido para usuario {user_id}")
        return False
    request_history[user_id].append(now)
    return True
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            plan        TEXT DEFAULT 'free',
            creado_en   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS portfolios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id    INTEGER NOT NULL,
            titulo        TEXT,
            datos         TEXT,
            html_generado TEXT,
            slug          TEXT UNIQUE,
            usuario_slug  TEXT,
            plantilla     TEXT DEFAULT 'oscuro',
            animacion     TEXT DEFAULT 'fade',
            visitas       INTEGER DEFAULT 0,
            password_hash TEXT,
            creado_en     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        );
        CREATE TABLE IF NOT EXISTS pagos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            plan       TEXT NOT NULL,
            importe    REAL NOT NULL,
            estado     TEXT DEFAULT 'pendiente',
            metodo     TEXT DEFAULT 'tarjeta',
            referencia TEXT,
            proveedor  TEXT DEFAULT 'ficticio',
            creado_en  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        );
        CREATE TABLE IF NOT EXISTS visitas_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            fecha        TEXT NOT NULL,
            referrer     TEXT,
            device_type  TEXT,
            FOREIGN KEY(portfolio_id) REFERENCES portfolios(id)
        );
        CREATE INDEX IF NOT EXISTS idx_visitas_log ON visitas_log(portfolio_id, fecha);
        CREATE TABLE IF NOT EXISTS mensajes_contacto (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            nombre       TEXT NOT NULL,
            email        TEXT NOT NULL,
            mensaje      TEXT NOT NULL,
            leido        INTEGER DEFAULT 0,
            creado_en    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(portfolio_id) REFERENCES portfolios(id)
        );
        CREATE TABLE IF NOT EXISTS portfolio_versiones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            datos        TEXT NOT NULL,
            html_generado TEXT NOT NULL,
            creado_en    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(portfolio_id) REFERENCES portfolios(id)
        );
        """)
        # Migraciones seguras para DBs existentes
        existing = {r[1] for r in db.execute("PRAGMA table_info(portfolios)").fetchall()}
        for col, ddl in [
            ("visitas",       "ALTER TABLE portfolios ADD COLUMN visitas INTEGER DEFAULT 0"),
            ("password_hash", "ALTER TABLE portfolios ADD COLUMN password_hash TEXT"),
            ("custom_slug",   "ALTER TABLE portfolios ADD COLUMN custom_slug TEXT"),
        ]:
            if col not in existing:
                db.execute(ddl)
        vlog_cols = {r[1] for r in db.execute("PRAGMA table_info(visitas_log)").fetchall()}
        for col, ddl in [
            ("referrer",    "ALTER TABLE visitas_log ADD COLUMN referrer TEXT"),
            ("device_type", "ALTER TABLE visitas_log ADD COLUMN device_type TEXT"),
        ]:
            if col not in vlog_cols:
                db.execute(ddl)

# Ejecutar al arranque (funciona con Gunicorn y con flask dev server)
init_db()

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()
def gen_slug():  return uuid.uuid4().hex[:10]

def make_sparkline_svg(values, width=80, height=28, color="#8b7eff"):
    """Genera un SVG sparkline con área rellena a partir de una lista de valores."""
    if not values or max(values) == 0:
        y = height // 2
        return Markup(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"><line x1="0" y1="{y}" x2="{width}" y2="{y}" stroke="rgba(255,255,255,0.08)" stroke-width="1.5"/></svg>')
    n   = len(values)
    mx  = max(values)
    pad = 3
    pts = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * (width - 2*pad) + pad if n > 1 else width / 2
        y = height - pad - (v / mx) * (height - 2*pad)
        pts.append((round(x,1), round(y,1)))
    path = "M " + " L ".join(f"{x},{y}" for x,y in pts)
    fill = path + f" L {pts[-1][0]},{height} L {pts[0][0]},{height} Z"
    return Markup(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{fill}" fill="{color}" opacity="0.15"/>'
        f'<path d="{path}" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )

def get_sparklines(db, portfolio_ids, days=14):
    """Devuelve {pid: [count_día_-N, ..., count_hoy]} para sparklines."""
    if not portfolio_ids:
        return {}
    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(days-1, -1, -1)]
    ph    = ",".join("?" * len(portfolio_ids))
    rows  = db.execute(
        f"SELECT portfolio_id, fecha, COUNT(*) as cnt FROM visitas_log "
        f"WHERE portfolio_id IN ({ph}) AND fecha >= ? GROUP BY portfolio_id, fecha",
        portfolio_ids + [dates[0]]
    ).fetchall()
    lookup = {(r["portfolio_id"], r["fecha"]): r["cnt"] for r in rows}
    return {pid: [lookup.get((pid, d), 0) for d in dates] for pid in portfolio_ids}

def gen_usuario_slug(db, nombre, user_id):
    """Genera un usuario_slug único a partir del nombre, añadiendo sufijo numérico si hay colisión."""
    base = re.sub(r'[^a-z0-9]', '', nombre.lower().strip())[:20]
    if not base:
        base = f"user{user_id}"
    candidate = base
    for n in range(2, 100):
        taken = db.execute("SELECT 1 FROM portfolios WHERE usuario_slug=?", (candidate,)).fetchone()
        if not taken:
            return candidate
        candidate = f"{base}{n}"
    return f"{base}{user_id}"

# ── OLLAMA ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres el asistente de Portify. Tu único objetivo es recopilar datos para crear un portfolio web profesional. Siempre respondes en ESPAÑOL.

════════════════════════════════
REGLA MÁS IMPORTANTE DE TODAS:
Recibirás un bloque [ESTADO ACTUAL] antes de cada mensaje del usuario.
Ese bloque lista qué datos ya tienes (✓) y cuáles faltan (✗).
NUNCA preguntes por un dato marcado con ✓. Ya lo tienes. Pasar a preguntar por ello de nuevo es un error grave.
════════════════════════════════

REGLAS DE COMPORTAMIENTO:
1. Lee siempre el [ESTADO ACTUAL] antes de responder.
2. Si el usuario da varios datos en un mensaje (p.ej. "Soy Ana, diseñadora UX"), extráelos todos y pregunta solo por el siguiente que falte.
3. Haz UNA sola pregunta por mensaje. Nunca dos a la vez.
4. Respuestas cortas y directas. Sin repetir lo que el usuario ya dijo.
5. No confirmes ni resumas lo que el usuario acaba de decir. Ve al grano.
6. Si el usuario responde algo vago, acéptalo y avanza.
7. Si el usuario dice "no tengo" o "ninguno", acéptalo y pasa al siguiente campo.
8. SIEMPRE en español. Nunca en inglés.

CAMPOS QUE NECESITAS RECOGER (en orden):
① nombre        — nombre completo
② rol           — profesión o estudios
③ descripcion   — quién es, en 2-3 frases
④ habilidades   — lista de skills, lenguajes, herramientas
⑤ proyectos     — 1 a 3 proyectos (nombre, qué hace, tecnologías, link si tiene)
⑥ experiencia   — trabajos o formación relevante (puede ser "ninguna")
⑦ contacto      — email y/o redes sociales
⑧ plantilla     — estilo visual del portfolio:
   🖤 Oscuro · ⚪ Minimalista · 🎨 Creativo · 📰 Editorial · 🌿 Orgánico
⑨ color         — color de acento:
   🌸 Rosa · 🌹 Frambuesa · 🌿 Morado · 🌊 Azul · 🍑 Melocotón
⑩ animacion     — efecto de entrada:
   ✨ Fade · ⬆️ Slide Up · 🔍 Zoom · 🌊 Float · ⌨️ Typewriter

CUANDO TENGAS TODOS LOS CAMPOS, responde ÚNICAMENTE con este JSON (sin texto antes ni después):
{"listo":true,"datos":{"nombre":"","rol":"","descripcion":"","habilidades":[],"proyectos":[{"titulo":"","descripcion":"","tecnologias":"","url":"","imagen":""}],"experiencia":[{"titulo":"","descripcion":""}],"email":"","redes":{"linkedin":"","github":"","twitter":"","instagram":"","youtube":"","tiktok":"","website":""},"plantilla":"oscuro","color":"#F18A8E","animacion":"fade"}}

MAPEOS PLANTILLA: oscuro/dark/tech→"oscuro" · minimalista/limpio/simple→"minimalista" · creativo/colorido→"creativo" · editorial/revista→"editorial" · orgánico/cálido/natural→"organico"
MAPEOS COLOR: rosa/coral→"#F18A8E" · frambuesa→"#E06A7C" · morado→"#6B5A7A" · azul/petróleo→"#3E627F" · melocotón→"#F2B38C"
MAPEOS ANIMACIÓN: fade/suave→"fade" · slide/subir→"slide-up" · zoom→"zoom" · float/flotar→"float" · typewriter/escribir→"typewriter" """


def build_context_note(parcial: dict) -> str:
    """Genera un bloque de estado que se inyecta antes de cada mensaje del usuario.
    Le dice al modelo exactamente qué datos ya tiene para que no los vuelva a pedir."""
    r = parcial.get("redes", {}) or {}
    tiene_contacto = bool(parcial.get("email") or any(r.values()))
    tiene_proyectos = bool(parcial.get("proyectos"))
    tiene_experiencia = bool(parcial.get("experiencia"))
    tiene_habilidades = bool(parcial.get("habilidades"))

    def mark(val):
        return "✓ YA LO TIENES" if val else "✗ falta"

    nombre     = parcial.get("nombre", "")
    rol        = parcial.get("rol", "")
    desc       = parcial.get("descripcion", "")
    habs       = ", ".join(parcial.get("habilidades", [])) if tiene_habilidades else ""
    n_projs    = len(parcial.get("proyectos", []))

    lines = [
        "[ESTADO ACTUAL — lee esto antes de responder]",
        f"① nombre       : {('\"' + nombre + '\"') if nombre else ''} {mark(nombre)}",
        f"② rol          : {('\"' + rol + '\"') if rol else ''} {mark(rol)}",
        f"③ descripcion  : {mark(desc)}",
        f"④ habilidades  : {habs if habs else ''} {mark(tiene_habilidades)}",
        f"⑤ proyectos    : {n_projs} recogido(s) {mark(tiene_proyectos)}",
        f"⑥ experiencia  : {mark(tiene_experiencia)}",
        f"⑦ contacto     : {mark(tiene_contacto)}",
        "⑧⑨⑩ plantilla/color/animacion: se recogen al final",
        "",
        "→ Pregunta SOLO por el primer campo marcado con ✗.",
        "→ NO menciones ni preguntes nada marcado con ✓.",
        "[FIN ESTADO]",
    ]
    return "\n".join(lines)

def chat_ollama(messages):
    try:
        r = requests.post(OLLAMA_URL, json={"model":OLLAMA_MODEL,"messages":messages,"stream":False}, timeout=120)
        r.raise_for_status()
        response_data = r.json()
        if "message" not in response_data or "content" not in response_data["message"]:
            logger.error(f"Respuesta inesperada de Ollama: {response_data}")
            return "⚠️ Ollama respondió de forma inesperada."
        return response_data["message"]["content"]
    except requests.exceptions.ConnectionError:
        logger.warning("Ollama no disponible")
        return "⚠️ Ollama no está corriendo. Ejecuta `ollama serve` en una terminal."
    except requests.exceptions.Timeout:
        logger.warning("Ollama timeout")
        return "⚠️ Ollama tardó demasiado. Inténtalo de nuevo."
    except Exception as e:
        logger.error(f"Error en chat_ollama: {e}")
        return f"⚠️ Error: {str(e)}"

def _clean_response_text(text):
    """Strips JSON blobs and code fences from assistant text before displaying."""
    clean = text
    for marker in ['{"listo"', '{ "listo"']:
        idx = clean.find(marker)
        if idx != -1:
            depth = 0
            for i, ch in enumerate(clean[idx:]):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        clean = clean[:idx] + clean[idx+i+1:]
                        break
            break
    clean = re.sub(r'```[\s\S]*?```', "", clean).strip()
    return clean or text

def parse_json(texto):
    if not texto: 
        return None
    try:
        s = texto.strip()
        if s.startswith("{") and "listo" in s: 
            return json.loads(s)
    except json.JSONDecodeError as e: 
        logger.debug(f"parse_json intento 1 falló: {e}")
    try:
        for marker in ['{"listo"','{ "listo"']:
            idx = texto.find(marker)
            if idx != -1:
                depth=0
                for i,ch in enumerate(texto[idx:]):
                    if ch=="{": depth+=1
                    elif ch=="}":
                        depth-=1
                        if depth==0:
                            try: 
                                return json.loads(texto[idx:idx+i+1])
                            except json.JSONDecodeError:
                                break
    except Exception as e:
        logger.debug(f"parse_json intento 2 falló: {e}")
    try:
        m = re.search(r'\{[^\{\}]*"listo"\s*:\s*true[^\{\}]*\}', texto, re.DOTALL)
        if m: 
            return json.loads(m.group())
    except Exception as e:
        logger.debug(f"parse_json intento 3 falló: {e}")
    logger.warning("No se pudo parsear JSON de respuesta de Ollama")
    return None


from datetime import datetime as _dt

# ── HELPERS ──────────────────────────────────────────────────────────────────

def _v(datos):
    r = datos.get("redes",{}) or {}
    color = datos.get("color","#F18A8E") or "#F18A8E"
    if not re.match(r'^#[0-9a-fA-F]{3,8}$', str(color)):
        color = "#F18A8E"
    animacion = datos.get("animacion","fade") or "fade"
    if animacion not in ANIMACIONES:
        animacion = "fade"
    raw_proyectos = datos.get("proyectos",[]) or []
    proyectos = []
    for p in raw_proyectos:
        if isinstance(p, dict):
            proyectos.append({
                "titulo":      str(escape(p.get("titulo","")      or "")),
                "descripcion": str(escape(p.get("descripcion","") or "")),
                "tecnologias": str(escape(p.get("tecnologias","") or "")),
                "url":    p.get("url","")    or "",
                "imagen": p.get("imagen","") or "",
            })
    raw_exp = datos.get("experiencia",[]) or []
    exp = []
    for e in raw_exp:
        if isinstance(e, dict):
            exp.append({
                "titulo":      str(escape(e.get("titulo","")      or "")),
                "descripcion": str(escape(e.get("descripcion","") or "")),
            })
        elif isinstance(e, str) and e.strip():
            exp.append(str(escape(e)))
    return dict(
        nombre=str(escape(datos.get("nombre","Tu Nombre") or "Tu Nombre")),
        rol=str(escape(datos.get("rol","Profesional") or "Profesional")),
        desc=str(escape(datos.get("descripcion","") or "")),
        skills=[str(escape(s)) for s in (datos.get("habilidades",[]) or []) if isinstance(s, str)],
        proyectos=proyectos,
        exp=exp,
        email=datos.get("email",""),
        linkedin=r.get("linkedin","") or "",
        github=r.get("github","") or "",
        twitter=r.get("twitter","") or "",
        instagram=r.get("instagram","") or "",
        youtube=r.get("youtube","") or "",
        tiktok=r.get("tiktok","") or "",
        website=r.get("website","") or "",
        foto=datos.get("foto_perfil","") or datos.get("foto","") or "",
        color=color,
        animacion=animacion,
        anio=_dt.now().year,
    )

def _ini(nombre):
    if not nombre:
        return "P"
    p = nombre.strip().split()
    if not p or not p[0]:
        return "P"
    if len(p) >= 2:
        return (p[0][0] + p[-1][0]).upper()
    return nombre.strip()[0].upper() if nombre.strip() else "P"

def _avatar(v, size=80, radius="50%"):
    c = v["color"]
    if v["foto"] and v["foto"].startswith("data:"):
        return '<img src="%s" style="width:%dpx;height:%dpx;border-radius:%s;object-fit:cover;display:block">' % (v["foto"], size, size, radius)
    ini = _ini(v["nombre"])
    fs = int(size*0.38)
    return '<div style="width:%dpx;height:%dpx;border-radius:%s;background:%s;color:#fff;display:flex;align-items:center;justify-content:center;font-size:%dpx;font-weight:700;flex-shrink:0">%s</div>' % (size, size, radius, c, fs, ini)

def _social_links(v, color):
    items = []
    if v["email"]:
        email = escape(v["email"])
        items.append('<a href="mailto:%s" style="color:%s;font-weight:500;font-size:.82rem">Email</a>' % (email, color))
    networks = [
        (v.get("website",""),  "Web"),
        (v.get("linkedin",""), "LinkedIn"),
        (v.get("github",""),   "GitHub"),
        (v.get("twitter",""),  "Twitter"),
        (v.get("instagram",""),"Instagram"),
        (v.get("youtube",""),  "YouTube"),
        (v.get("tiktok",""),   "TikTok"),
    ]
    for url, lb in networks:
        if url and url not in ["#","ninguna","none",""]:
            if not url.startswith("http"): url = "https://" + url
            url = escape(url)
            items.append('<a href="%s" target="_blank" style="color:%s;font-weight:500;font-size:.82rem">%s</a>' % (url, color, lb))
    return "".join(items)

def _btns(v, s_primary, s_secondary):
    out = []
    if v["email"]:
        email = escape(v["email"])
        out.append('<a href="mailto:%s" style="%s">✉ Email</a>' % (email, s_primary))
    networks = [
        (v.get("website",""),  "🌐 Web"),
        (v.get("linkedin",""), "LinkedIn"),
        (v.get("github",""),   "GitHub"),
        (v.get("twitter",""),  "Twitter"),
        (v.get("instagram",""),"Instagram"),
        (v.get("youtube",""),  "YouTube"),
        (v.get("tiktok",""),   "TikTok"),
    ]
    for url, lb in networks:
        if url and url not in ["#","ninguna","none",""]:
            if not url.startswith("http"): url = "https://" + url
            url = escape(url)
            out.append('<a href="%s" target="_blank" style="%s">%s</a>' % (url, s_secondary, lb))
    return "".join(out)

def _proj_img(p, c, h=200):
    img = p.get("imagen","") or ""
    if img and (img.startswith("data:") or img.startswith("http")):
        return '<div style="height:%dpx;overflow:hidden"><img src="%s" style="width:100%%;height:100%%;object-fit:cover"></div>' % (h, img)
    tec = (p.get("tecnologias","") or "")[:18]
    return (
        '<div style="height:%dpx;background:linear-gradient(135deg,%s44,%s18);'
        'display:flex;align-items:center;justify-content:center;position:relative">'
        '<svg width="56" height="56" viewBox="0 0 64 64" fill="none">'
        '<rect x="8" y="14" width="48" height="36" rx="4" stroke="%s" stroke-width="2" fill="none" opacity=".5"/>'
        '<circle cx="22" cy="26" r="5" fill="%s" opacity=".4"/>'
        '<path d="M8 40l14-10 10 8 8-7 16 12" stroke="%s" stroke-width="2" stroke-linecap="round" opacity=".5"/>'
        '</svg>'
        '<span style="position:absolute;bottom:8px;right:10px;font-size:.68rem;color:%s;opacity:.7;font-weight:600">%s</span>'
        '</div>'
    ) % (h, c, c, c, c, c, c, tec)

def _proj_url(p):
    url = (p.get("url","") or "").strip()
    if not url or url in ["#","ninguna","none",""]:
        return ""
    # Validar y normalizar URL
    if url.startswith("http://") or url.startswith("https://"):
        pass  # URL válida
    elif url.startswith("www."):
        url = "https://" + url
    else:
        url = "https://" + url
    # Escapar atributo href
    url = escape(url)
    return '<a href="%s" target="_blank" style="font-size:.78rem;font-weight:600;display:inline-flex;align-items:center;gap:3px">Ver proyecto ↗</a>' % url

def _exp_html(exp, dot, tc, mc):
    out = []
    for e in (exp or []):
        if isinstance(e, dict):
            t, d = e.get("titulo",""), e.get("descripcion","")
        elif isinstance(e, str) and e.strip():
            t, d = "", e
        else:
            continue
        title_html = '<strong style="display:block;font-weight:600;font-size:.92rem;margin-bottom:4px;color:%s">%s</strong>' % (tc, t) if t else ""
        out.append(
            '<div class="anim-el" style="display:grid;grid-template-columns:18px 1fr;gap:14px;padding-bottom:22px">'
            '<div style="width:9px;height:9px;border-radius:50%%;background:%s;margin-top:5px;box-shadow:0 0 8px %s66"></div>'
            '<div>%s<p style="color:%s;font-size:.88rem;line-height:1.75;margin:0">%s</p></div>'
            '</div>' % (dot, dot, title_html, mc, d)
        )
    return "".join(out)

def _anim_css(anim):
    base = (
        "@keyframes _fIn{from{opacity:0}to{opacity:1}}"
        "@keyframes _sUp{from{opacity:0;transform:translateY(32px)}to{opacity:1;transform:none}}"
        "@keyframes _sLt{from{opacity:0;transform:translateX(32px)}to{opacity:1;transform:none}}"
        "@keyframes _zIn{from{opacity:0;transform:scale(.88)}to{opacity:1;transform:scale(1)}}"
        "@keyframes _fl{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}"
        ".anim-el{opacity:0;animation-fill-mode:both;animation-duration:.65s;animation-timing-function:cubic-bezier(.4,0,.2,1)}"
        ".anim-el.vis{opacity:1}"
    )
    m = {
        "fade":       ".anim-el.vis{animation-name:_fIn}",
        "slide-up":   ".anim-el.vis{animation-name:_sUp}",
        "slide-left": ".anim-el.vis{animation-name:_sLt}",
        "zoom":       ".anim-el.vis{animation-name:_zIn}",
        "float":      ".anim-el{opacity:1!important}.anim-el.vis{animation-name:_fl;animation-duration:3s;animation-iteration-count:infinite;animation-timing-function:ease-in-out}",
        "typewriter": "",
    }
    delays = "".join(".anim-el:nth-child(%d){animation-delay:%.2fs}" % (i,i*0.08) for i in range(1,16))
    return base + m.get(anim, m["fade"]) + delays

_ANIM_JS = ('<script>(function(){'
    'var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting)e.target.classList.add("vis")});},{threshold:.12});'
    'document.querySelectorAll(".anim-el").forEach(function(el){io.observe(el)});'
    '})();</script>')

def _stats(v, c):
    n, s = len(v["proyectos"]), len(v["skills"])
    if not n and not s: return ""
    items = []
    if n: items.append('<div><div style="font-size:2rem;font-weight:700;color:%s">%d+</div><div style="font-size:.7rem;color:#aaa;letter-spacing:.06em;text-transform:uppercase">Proyectos</div></div>' % (c,n))
    if s: items.append('<div><div style="font-size:2rem;font-weight:700;color:%s">%d+</div><div style="font-size:.7rem;color:#aaa;letter-spacing:.06em;text-transform:uppercase">Skills</div></div>' % (c,s))
    return '<div style="display:flex;gap:24px;margin-top:24px">%s</div>' % "".join(items)

def _stats_light(v, c, muted):
    n, s = len(v["proyectos"]), len(v["skills"])
    if not n and not s: return ""
    items = []
    if n: items.append('<div><div style="font-size:1.9rem;font-weight:700;color:%s">%d+</div><div style="font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:%s">Proyectos</div></div>' % (c,n,muted))
    if s: items.append('<div><div style="font-size:1.9rem;font-weight:700;color:%s">%d+</div><div style="font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:%s">Skills</div></div>' % (c,s,muted))
    return '<div style="display:flex;gap:22px;margin-bottom:26px;padding-bottom:26px;border-bottom:1px solid rgba(0,0,0,.08)">%s</div>' % "".join(items)

# ── GENERADOR PRINCIPAL ───────────────────────────────────────────────────────

def _inject_head_tags(html: str, nombre: str, color: str, canonical_url: str) -> str:
    """Inyecta OG tags y favicon en el <head> de un HTML ya generado."""
    from agent_portfolio import _og_tags, _favicon
    og      = _og_tags(nombre, "", "", "", canonical_url, color)
    favicon = _favicon(nombre, color)
    return html.replace("</title>", f"</title>{og}{favicon}", 1)

_LEGACY = {"oscuro","minimalista","creativo","editorial","organico"}
_LEGACY_FN = None  # se define abajo tras los generadores legacy

def generar_html(datos, portfolio_id=None):
    p = datos.get("plantilla", "oscuro")
    # All templates now use the universal generator
    return generar_html_universal(datos, portfolio_id=portfolio_id)




def _oscuro(datos):
    v=_v(datos); c=v["color"]; ac=_anim_css(v["animacion"])
    nombre1 = v["nombre"].split()[0] if " " in v["nombre"] else v["nombre"]
    nombre2 = " ".join(v["nombre"].split()[1:]) if " " in v["nombre"] else ""
    
    skills_html = "".join(
        '<span class="anim-el" style="padding:8px 16px;border-radius:8px;background:rgba(255,255,255,.06);'
        'border:1px solid rgba(255,255,255,.1);font-size:.85rem;font-weight:500;color:#c8c8d8">'+s+'</span>'
        for s in v["skills"]
    )
    
    projs_html = ""
    for i,p in enumerate(v["proyectos"]):
        projs_html += (
            '<article class="anim-el" style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);'
            'border-radius:16px;overflow:hidden;animation-delay:'+str(i*0.1)+'s">'
            + _proj_img(p,c,200)
            + '<div style="padding:20px">'
            '<h4 style="font-family:Instrument Serif,serif;font-size:1.1rem;font-weight:400;margin-bottom:8px;color:#ededf5">'+p.get("titulo","")+'</h4>'
            '<p style="color:#a0a0b8;font-size:.88rem;margin-bottom:14px;line-height:1.7">'+p.get("descripcion","")+'</p>'
            '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">'
            '<span style="padding:4px 10px;border-radius:6px;background:rgba(255,255,255,.05);font-size:.75rem;color:#a0a0b8">'+p.get("tecnologias","")+'</span>'
            '<span style="color:'+c+'">'+_proj_url(p)+'</span>'
            '</div></div></article>'
        )
    
    ex_html = _exp_html(v["exp"], c, "#ededf5", "#a0a0b8")
    bp = "padding:12px 24px;border-radius:10px;background:"+c+";color:#fff;font-weight:600;font-size:.9rem;border:none;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bs = "padding:12px 24px;border-radius:10px;background:transparent;color:"+c+";font-weight:600;font-size:.9rem;border:1px solid "+c+";text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    btns_html = _btns(v, bp, bs)
    card_skills = "".join('<span style="padding:5px 10px;border-radius:7px;background:rgba(255,255,255,.06);font-size:.75rem;color:#a0a0b8">'+s+'</span>' for s in v["skills"][:6])
    social = _social_links(v, c)
    social_row = ('<div style="width:100%;height:1px;background:rgba(255,255,255,.07);margin:14px 0"></div>'
                  '<div style="display:flex;gap:12px;flex-wrap:wrap;justify-content:center">'+social+'</div>') if social else ""
    n_p, n_s = len(v["proyectos"]), len(v["skills"])
    stats_parts = []
    if n_p: stats_parts.append('<div><div style="font-size:2rem;font-weight:700;color:'+c+'">'+str(n_p)+'+</div><div style="font-size:.7rem;color:#aaa;letter-spacing:.06em;text-transform:uppercase">Proyectos</div></div>')
    if n_s: stats_parts.append('<div><div style="font-size:2rem;font-weight:700;color:'+c+'">'+str(n_s)+'+</div><div style="font-size:.7rem;color:#aaa;letter-spacing:.06em;text-transform:uppercase">Skills</div></div>')
    stats = '<div style="display:flex;gap:24px;margin-top:24px">'+"".join(stats_parts)+'</div>' if stats_parts else ""
    
    skills_sec = ('<section id="skills" style="padding:60px 0;border-top:1px solid rgba(255,255,255,.06)">'
                  '<div class="n"><div class="sl"><h2>Habilidades</h2></div>'
                  '<div style="display:flex;flex-wrap:wrap;gap:10px">'+skills_html+'</div></div></section>') if skills_html else ""
    proj_sec   = ('<section id="proyectos" style="border-top:1px solid rgba(255,255,255,.06)">'
                  '<div class="w"><div class="sl"><h2>Proyectos</h2></div>'
                  '<div class="pg">'+projs_html+'</div></div></section>') if projs_html else ""
    exp_sec    = ('<section id="experiencia" style="border-top:1px solid rgba(255,255,255,.06)">'
                  '<div class="n"><div class="sl"><h2>Experiencia</h2></div>'
                  '<div>'+ex_html+'</div></div></section>') if ex_html else ""

    css_body = (
        "*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}"
        "body{font-family:DM Sans,sans-serif;background:#080810;color:#ededf5;line-height:1.65;min-height:100vh}"
        "a{text-decoration:none;color:inherit}"
        ".w{width:min(1100px,calc(100% - 48px));margin:0 auto}.n{width:min(780px,calc(100% - 48px));margin:0 auto}"
        "nav{position:sticky;top:0;z-index:100;background:rgba(8,8,16,.85);backdrop-filter:blur(20px);"
        "border-bottom:1px solid rgba(255,255,255,.06);padding:14px 0}"
        ".nav-i{display:flex;align-items:center;justify-content:space-between;gap:20px}"
        ".nav-logo{font-family:Instrument Serif,serif;font-size:1.1rem;background:linear-gradient(135deg,"+c+",#7c6dfa);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}"
        ".nl{display:flex;gap:4px}.nl a{padding:5px 12px;border-radius:7px;color:#a0a0b8;font-size:.82rem;font-weight:500;transition:.15s}"
        ".nl a:hover{color:#ededf5;background:rgba(255,255,255,.06)}"
        "section{padding:80px 0}"
        "h2{font-family:Instrument Serif,serif;font-size:2rem;font-weight:400;letter-spacing:-.02em;margin-bottom:28px}"
        ".sl{display:flex;align-items:center;gap:16px;margin-bottom:32px}.sl h2{margin:0}"
        ".sl::after{content:\'\';flex:1;height:1px;background:rgba(255,255,255,.07)}"
        ".pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}"
        "footer{padding:32px 0;border-top:1px solid rgba(255,255,255,.06);text-align:center;color:#3a3a4a;font-size:.8rem}"
        "@media(max-width:860px){.nl{display:none}.hg{grid-template-columns:1fr!important}}"
    )
    
    html = (
        "<!DOCTYPE html><html lang=\"es\"><head>"
        "<meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>"+v["nombre"]+" &middot; Portfolio</title>"
        "<link href=\"https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap\" rel=\"stylesheet\">"
        "<style>"+ac+css_body+"</style></head><body>"
        "<nav><div class=\"w nav-i\">"
        "<span class=\"nav-logo\">"+nombre1+"</span>"
        "<div class=\"nl\"><a href=\"#skills\">Skills</a><a href=\"#proyectos\">Proyectos</a><a href=\"#contacto\">Contacto</a></div>"
        "</div></nav>"
        
        "<section style=\"padding:100px 0 80px;position:relative;overflow:hidden\">"
        "<div style=\"position:absolute;top:-200px;right:-100px;width:700px;height:700px;border-radius:50%;"
        "background:radial-gradient(circle,"+c+"12,transparent 65%);filter:blur(60px);pointer-events:none\"></div>"
        "<div class=\"w hg\" style=\"display:grid;grid-template-columns:1fr 380px;gap:60px;align-items:center;position:relative;z-index:1\">"
        
        "<div class=\"anim-el\">"
        "<div style=\"display:inline-flex;align-items:center;gap:6px;padding:4px 14px;border-radius:999px;"
        "background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);font-size:.7rem;font-weight:600;"
        "letter-spacing:.08em;text-transform:uppercase;color:#a0a0b8;margin-bottom:22px\">"
        "<span style=\"width:5px;height:5px;border-radius:50%;background:"+c+";display:inline-block\"></span>"
        "Portfolio &middot; "+str(v["anio"])+"</div>"
        "<h1 style=\"font-family:Instrument Serif,serif;font-size:clamp(3rem,5.5vw,5.5rem);"
        "line-height:.9;letter-spacing:-.04em;font-weight:400;margin-bottom:14px\">"
        +nombre1+"<br><em style=\"font-style:italic;color:"+c+"\">"+nombre2+"</em></h1>"
        "<p style=\"color:"+c+";font-size:1rem;font-weight:500;margin-bottom:16px\">"+v["rol"]+"</p>"
        "<p style=\"color:#a0a0b8;font-size:.97rem;max-width:500px;line-height:1.85;font-weight:300\">"+v["desc"]+"</p>"
        +stats+
        "<div style=\"display:flex;gap:12px;margin-top:28px;flex-wrap:wrap\">"+btns_html+"</div>"
        "</div>"
        
        "<div class=\"anim-el\" style=\"animation-delay:.15s\">"
        "<div style=\"background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);"
        "border-radius:24px;padding:32px;position:relative;overflow:hidden\">"
        "<div style=\"position:absolute;top:-60px;right:-60px;width:180px;height:180px;border-radius:50%;"
        "background:radial-gradient(circle,"+c+"15,transparent 70%)\"></div>"
        "<div style=\"position:relative;display:flex;flex-direction:column;align-items:center;text-align:center;gap:14px\">"
        +_avatar(v,88,"18px")+
        "<div><h3 style=\"font-family:Instrument Serif,serif;font-size:1.35rem;font-weight:400;margin-bottom:4px\">"+v["nombre"]+"</h3>"
        "<p style=\"color:"+c+";font-size:.85rem;font-weight:600\">"+v["rol"]+"</p></div>"
        "<div style=\"display:flex;flex-wrap:wrap;gap:6px;justify-content:center\">"+card_skills+"</div>"
        +social_row+
        "</div></div></div>"
        
        "</div></section>"
        +skills_sec+proj_sec+exp_sec+
        
        "<section id=\"contacto\" style=\"border-top:1px solid rgba(255,255,255,.06)\">"
        "<div class=\"n\"><div class=\"anim-el\" style=\"background:rgba(255,255,255,.025);"
        "border:1px solid rgba(255,255,255,.07);border-radius:24px;padding:56px;text-align:center;"
        "position:relative;overflow:hidden\">"
        "<div style=\"position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,"+c+"10,transparent 60%);pointer-events:none\"></div>"
        "<div style=\"position:relative\">"
        "<h2 style=\"margin-bottom:12px\">Hablamos?</h2>"
        "<p style=\"color:#a0a0b8;margin-bottom:28px;font-size:.97rem\">Abierto a oportunidades, colaboraciones y proyectos.</p>"
        "<div style=\"display:flex;gap:12px;justify-content:center;flex-wrap:wrap\">"+btns_html+"</div>"
        "</div></div></div></section>"
        "<footer><div class=\"w\"><p>Creado con <strong style=\"color:"+c+"\">Portify</strong> &middot; "+str(v["anio"])+"</p></div></footer>"
        +_ANIM_JS+
        "</body></html>"
    )
    return html


def _minimalista(datos):
    v=_v(datos); c=v["color"]; ac=_anim_css(v["animacion"])
    skills_html = "".join('<span class="anim-el" style="padding:7px 14px;border:1px solid #e0dcd8;font-size:.82rem;color:#555">'+s+'</span>' for s in v["skills"])
    projs_html = ""
    for i,p in enumerate(v["proyectos"]):
        img_h = ('<div style="height:160px;overflow:hidden;border-radius:3px;margin-bottom:14px">'
                 '<img src="'+p["imagen"]+'" style="width:100%;height:100%;object-fit:cover"></div>') if p.get("imagen") and (p["imagen"].startswith("data:") or p["imagen"].startswith("http")) else ""
        projs_html += ('<div class="anim-el" style="display:grid;grid-template-columns:64px 1fr;gap:20px;padding:24px 0;border-bottom:1px solid #e8e4e0;align-items:start">'
            '<span style="font-family:Playfair Display,serif;font-size:2.8rem;font-weight:700;color:#ddd;line-height:1">'+str(i+1).zfill(2)+'</span>'
            '<div>'+img_h+'<h4 style="font-family:Playfair Display,serif;font-size:1.15rem;margin-bottom:8px;color:#1a1a1a">'+p.get("titulo","")+'</h4>'
            '<p style="color:#555;font-size:.9rem;margin-bottom:10px;line-height:1.8;font-weight:300">'+p.get("descripcion","")+'</p>'
            '<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
            '<span style="font-size:.73rem;color:#aaa;letter-spacing:.05em;text-transform:uppercase">'+p.get("tecnologias","")+'</span>'
            '<span style="color:'+c+'">'+_proj_url(p)+'</span>'
            '</div></div></div>')
    ex_html = _exp_html(v["exp"], c, "#1a1a1a", "#666")
    bp = "padding:10px 22px;border-radius:3px;border:1px solid #1a1a1a;color:#1a1a1a;font-weight:500;font-size:.88rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bs = "padding:10px 22px;border-radius:3px;border:1px solid "+c+";color:"+c+";font-weight:500;font-size:.88rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    btns_html = _btns(v,bp,bs)
    card_skills = "".join('<span style="padding:3px 9px;border:1px solid #e0dcd8;font-size:.72rem;color:#888">'+s+'</span>' for s in v["skills"][:6])
    n_p,n_s = len(v["proyectos"]),len(v["skills"])
    stats_p = []
    if n_p: stats_p.append('<div><div style="font-family:Playfair Display,serif;font-size:1.8rem;color:'+c+'">'+str(n_p)+'+</div><div style="font-size:.68rem;color:#aaa;letter-spacing:.08em;text-transform:uppercase">Proyectos</div></div>')
    if n_s: stats_p.append('<div><div style="font-family:Playfair Display,serif;font-size:1.8rem;color:'+c+'">'+str(n_s)+'+</div><div style="font-size:.68rem;color:#aaa;letter-spacing:.08em;text-transform:uppercase">Skills</div></div>')
    stats = ('<div style="display:flex;gap:24px;margin-bottom:26px;padding-bottom:26px;border-bottom:1px solid #e8e4e0">'+"".join(stats_p)+"</div>") if stats_p else ""
    proj_sec = ('<section id="proyectos"><div class="w"><h2>Proyectos</h2><div>'+projs_html+'</div></div></section>') if projs_html else ""
    skills_sec = ('<section id="skills"><div class="n"><h2>Habilidades</h2><div style="display:flex;flex-wrap:wrap;gap:8px">'+skills_html+'</div></div></section>') if skills_html else ""
    exp_sec = ('<section id="experiencia"><div class="n"><h2>Experiencia</h2><div>'+ex_html+'</div></div></section>') if ex_html else ""
    css = ("*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}"
           "body{font-family:Inter,sans-serif;background:#fafaf8;color:#1a1a1a;line-height:1.7}a{text-decoration:none;color:inherit}"
           ".w{width:min(1100px,calc(100% - 48px));margin:0 auto}.n{width:min(740px,calc(100% - 48px));margin:0 auto}"
           "nav{position:sticky;top:0;z-index:100;background:#fafaf8;border-bottom:1px solid #e8e4e0;padding:18px 0}"
           ".nav-i{display:flex;align-items:center;justify-content:space-between}"
           ".nav-logo{font-family:Playfair Display,serif;font-size:1.15rem;color:#1a1a1a}"
           ".nl{display:flex;gap:24px}.nl a{color:#888;font-size:.78rem;font-weight:500;letter-spacing:.07em;text-transform:uppercase;transition:.15s}.nl a:hover{color:#1a1a1a}"
           "section{padding:80px 0;border-top:1px solid #e8e4e0}h2{font-family:Playfair Display,serif;font-size:2.2rem;font-weight:700;letter-spacing:-.03em;margin-bottom:28px}"
           "footer{padding:32px 0;text-align:center;color:#aaa;font-size:.78rem;border-top:1px solid #e8e4e0}"
           "@media(max-width:860px){.nl{display:none}.hg{grid-template-columns:1fr!important}}")
    return ("<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>"+v["nombre"]+" &middot; Portfolio</title>"
        "<link href=\"https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500&display=swap\" rel=\"stylesheet\">"
        "<style>"+ac+css+"</style></head><body>"
        "<nav><div class=\"w nav-i\"><span class=\"nav-logo\">"+v["nombre"]+"</span>"
        "<div class=\"nl\"><a href=\"#proyectos\">Proyectos</a><a href=\"#skills\">Skills</a><a href=\"#contacto\">Contacto</a></div></div></nav>"
        "<section style=\"border-top:none;padding:120px 0 80px\">"
        "<div class=\"w hg\" style=\"display:grid;grid-template-columns:1fr 280px;gap:64px;align-items:start\">"
        "<div class=\"anim-el\"><p style=\"font-size:.7rem;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:#aaa;margin-bottom:18px\">Portfolio &middot; "+str(v["anio"])+"</p>"
        "<h1 style=\"font-family:Playfair Display,serif;font-size:clamp(3.5rem,6vw,6rem);line-height:.88;letter-spacing:-.03em;font-weight:700;margin-bottom:20px\">"+v["nombre"]+"</h1>"
        "<p style=\"color:"+c+";font-size:.9rem;font-weight:500;letter-spacing:.06em;text-transform:uppercase;margin-bottom:18px\">"+v["rol"]+"</p>"
        "<p style=\"color:#555;font-size:.95rem;max-width:480px;line-height:1.9;font-weight:300;margin-bottom:26px\">"+v["desc"]+"</p>"
        +stats+"<div style=\"display:flex;gap:10px;flex-wrap:wrap\">"+btns_html+"</div></div>"
        "<div class=\"anim-el\" style=\"animation-delay:.15s;border-left:2px solid "+c+";padding-left:24px\">"
        +_avatar(v,72,"50%")+
        "<h3 style=\"font-family:Playfair Display,serif;font-size:1.2rem;margin:14px 0 3px\">"+v["nombre"]+"</h3>"
        "<p style=\"color:"+c+";font-size:.78rem;font-weight:500;text-transform:uppercase;letter-spacing:.06em;margin-bottom:16px\">"+v["rol"]+"</p>"
        "<div style=\"display:flex;flex-wrap:wrap;gap:5px\">"+card_skills+"</div>"
        "</div></div></section>"
        +proj_sec+skills_sec+exp_sec+
        "<section id=\"contacto\"><div class=\"n\"><div class=\"anim-el\" style=\"border:1px solid #e8e4e0;padding:56px;text-align:center\">"
        "<h2 style=\"margin-bottom:12px\">Hablamos?</h2>"
        "<p style=\"color:#666;margin-bottom:28px\">Tienes una propuesta? Me encantara escucharte.</p>"
        "<div style=\"display:flex;gap:10px;justify-content:center;flex-wrap:wrap\">"+btns_html+"</div>"
        "</div></div></section>"
        "<footer><div class=\"w\"><p>"+v["nombre"]+" &middot; Creado con Portify</p></div></footer>"
        +_ANIM_JS+"</body></html>")


def _creativo(datos):
    v=_v(datos); c=v["color"]; ac=_anim_css(v["animacion"])
    nombre1 = v["nombre"].split()[0] if " " in v["nombre"] else v["nombre"]
    nombre2 = " ".join(v["nombre"].split()[1:]) if " " in v["nombre"] else ""
    skills_html = "".join('<span class="anim-el" style="padding:9px 18px;border-radius:999px;border:2px solid #111;font-size:.85rem;font-weight:700;color:#111">'+s+'</span>' for s in v["skills"])
    projs_html = ""
    for i,p in enumerate(v["proyectos"]):
        projs_html += ('<article class="anim-el" style="border:2px solid #111;border-radius:16px;overflow:hidden;animation-delay:'+str(i*0.1)+'s">'
            +_proj_img(p,c,200)+
            '<div style="padding:20px"><h4 style="font-size:1rem;font-weight:700;margin-bottom:8px;color:#111">'+p.get("titulo","")+'</h4>'
            '<p style="color:#555;font-size:.85rem;margin-bottom:12px;line-height:1.7">'+p.get("descripcion","")+'</p>'
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">'
            '<span style="padding:4px 12px;border-radius:999px;border:1px solid #ddd;font-size:.75rem;color:#777">'+p.get("tecnologias","")+'</span>'
            '<span style="color:'+c+';font-weight:700">'+_proj_url(p)+'</span>'
            '</div></div></article>')
    ex_html = _exp_html(v["exp"], c, "#111", "#555")
    bp = "padding:13px 26px;border-radius:999px;border:2px solid #111;color:#111;font-weight:700;font-size:.9rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bs = "padding:13px 26px;border-radius:999px;border:2px solid "+c+";color:"+c+";font-weight:700;font-size:.9rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bp_inv = "padding:12px 24px;border-radius:999px;border:2px solid #fff;color:#fff;font-weight:700;font-size:.9rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bs_inv = "padding:12px 24px;border-radius:999px;border:2px solid "+c+";color:"+c+";font-weight:700;font-size:.9rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    btns_html = _btns(v,bp,bs); btns_inv = _btns(v,bp_inv,bs_inv)
    card_skills = "".join('<span style="padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.1);font-size:.72rem;color:rgba(255,255,255,.7)">'+s+'</span>' for s in v["skills"][:6])
    n_p,n_s = len(v["proyectos"]),len(v["skills"])
    stats_p = []
    if n_p: stats_p.append('<div><div style="font-size:2rem;font-weight:700;color:'+c+'">'+str(n_p)+'+</div><div style="font-size:.7rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em">Proyectos</div></div>')
    if n_s: stats_p.append('<div><div style="font-size:2rem;font-weight:700;color:'+c+'">'+str(n_s)+'+</div><div style="font-size:.7rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em">Skills</div></div>')
    stats = ('<div style="display:flex;gap:20px;margin-bottom:24px">'+"".join(stats_p)+"</div>") if stats_p else ""
    skills_sec = ('<section id="skills"><div class="n"><div class="sl"><h2>Habilidades</h2></div><div style="display:flex;flex-wrap:wrap;gap:8px">'+skills_html+'</div></div></section>') if skills_html else ""
    proj_sec = ('<section id="proyectos" style="border-top:1px solid #eee"><div class="w"><div class="sl"><h2>Proyectos</h2></div><div class="pg">'+projs_html+'</div></div></section>') if projs_html else ""
    exp_sec = ('<section id="experiencia" style="border-top:1px solid #eee"><div class="n"><div class="sl"><h2>Experiencia</h2></div><div>'+ex_html+'</div></div></section>') if ex_html else ""
    css = ("*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}"
           "body{font-family:Space Grotesk,sans-serif;background:#fff;color:#111;line-height:1.65}a{text-decoration:none;color:inherit}"
           ".w{width:min(1100px,calc(100% - 48px));margin:0 auto}.n{width:min(780px,calc(100% - 48px));margin:0 auto}"
           "nav{position:sticky;top:0;z-index:100;background:#fff;border-bottom:3px solid #111;padding:14px 0}"
           ".nav-i{display:flex;align-items:center;justify-content:space-between}"
           ".nav-logo{font-weight:700;font-size:1.05rem;color:#111}"
           ".nl{display:flex;gap:24px}.nl a{color:#666;font-size:.85rem;font-weight:600;transition:.15s}.nl a:hover{color:#111}"
           "section{padding:72px 0}h2{font-size:2rem;font-weight:700;letter-spacing:-.04em;margin-bottom:28px}"
           ".sl{display:flex;align-items:center;gap:14px;margin-bottom:28px}.sl h2{margin:0}.sl::after{content:\'\';flex:1;height:3px;background:#111}"
           ".pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}"
           "footer{padding:28px 0;text-align:center;color:#888;font-size:.78rem;border-top:3px solid #111}"
           "@media(max-width:860px){.nl{display:none}.hg{grid-template-columns:1fr!important}}")
    return ("<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>"+v["nombre"]+" &middot; Portfolio</title>"
        "<link href=\"https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap\" rel=\"stylesheet\">"
        "<style>"+ac+css+"</style></head><body>"
        "<nav><div class=\"w nav-i\"><span class=\"nav-logo\">"+v["nombre"]+"</span>"
        "<div class=\"nl\"><a href=\"#proyectos\">Proyectos</a><a href=\"#skills\">Skills</a><a href=\"#contacto\">Contacto</a></div></div></nav>"
        "<section style=\"padding:80px 0 60px;background:linear-gradient(135deg,"+c+"10,transparent 55%)\">"
        "<div class=\"w hg\" style=\"display:grid;grid-template-columns:1fr 300px;gap:52px;align-items:center\">"
        "<div class=\"anim-el\">"
        "<span style=\"display:inline-flex;padding:6px 16px;border-radius:999px;background:"+c+";color:#fff;font-size:.72rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:20px\">Portfolio Creativo &middot; "+str(v["anio"])+"</span>"
        "<h1 style=\"font-size:clamp(3rem,5.5vw,5rem);line-height:.88;letter-spacing:-.06em;font-weight:700;margin-bottom:16px\">"
        +nombre1+"<br><span style=\"color:"+c+"\">"+nombre2+"</span></h1>"
        "<p style=\"color:#444;font-size:.97rem;font-weight:500;margin-bottom:14px\">"+v["rol"]+"</p>"
        "<p style=\"color:#555;font-size:.9rem;max-width:480px;line-height:1.85;margin-bottom:20px\">"+v["desc"]+"</p>"
        +stats+"<div style=\"display:flex;gap:10px;flex-wrap:wrap\">"+btns_html+"</div></div>"
        "<div class=\"anim-el\" style=\"animation-delay:.15s;background:#111;border-radius:20px;padding:28px;color:#fff;text-align:center\">"
        +_avatar(v,80,"50%")+
        "<h3 style=\"font-size:1.2rem;font-weight:700;margin:14px 0 4px\">"+v["nombre"]+"</h3>"
        "<p style=\"color:"+c+";font-size:.82rem;font-weight:600;margin-bottom:16px\">"+v["rol"]+"</p>"
        "<div style=\"display:flex;flex-wrap:wrap;gap:5px;justify-content:center\">"+card_skills+"</div>"
        "</div></div></section>"
        +skills_sec+proj_sec+exp_sec+
        "<section id=\"contacto\" style=\"border-top:1px solid #eee\"><div class=\"n\">"
        "<div class=\"anim-el\" style=\"background:#111;border-radius:20px;padding:56px;text-align:center;color:#fff\">"
        "<h2 style=\"color:#fff;margin-bottom:12px\">Hablamos?</h2>"
        "<p style=\"color:rgba(255,255,255,.55);margin-bottom:28px\">Siempre abierto a nuevas ideas y colaboraciones.</p>"
        "<div style=\"display:flex;gap:10px;justify-content:center;flex-wrap:wrap\">"+btns_inv+"</div>"
        "</div></div></section>"
        "<footer><div class=\"w\"><p>"+v["nombre"]+" &middot; Portify "+str(v["anio"])+"</p></div></footer>"
        +_ANIM_JS+"</body></html>")


def _editorial(datos):
    v=_v(datos); c=v["color"]; ac=_anim_css(v["animacion"])
    nombre1 = v["nombre"].split()[0] if " " in v["nombre"] else v["nombre"]
    nombre2 = " ".join(v["nombre"].split()[1:]) if " " in v["nombre"] else ""
    skills_html = "".join('<span class="anim-el" style="padding:6px 14px;border:1px solid #c4b890;font-size:.82rem;color:#5a4a2a">'+s+'</span>' for s in v["skills"])
    projs_html = ""
    for i,p in enumerate(v["proyectos"]):
        img_h = ('<div style="height:160px;overflow:hidden;margin-bottom:14px"><img src="'+p["imagen"]+'" style="width:100%;height:100%;object-fit:cover"></div>') if p.get("imagen") and (p["imagen"].startswith("data:") or p["imagen"].startswith("http")) else ""
        projs_html += ('<div class="anim-el" style="display:grid;grid-template-columns:80px 1fr;gap:20px;padding:22px 0;border-bottom:1px solid #d4c8a8;align-items:start">'
            '<span style="font-family:DM Serif Display,serif;font-size:3rem;color:#d4c8a8;line-height:1">'+str(i+1).zfill(2)+'</span>'
            '<div>'+img_h+'<h4 style="font-family:DM Serif Display,serif;font-size:1.2rem;margin-bottom:8px;color:#1a1208">'+p.get("titulo","")+'</h4>'
            '<p style="color:#5a4a2a;font-size:.88rem;margin-bottom:10px;line-height:1.8;font-weight:300">'+p.get("descripcion","")+'</p>'
            '<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
            '<span style="font-size:.72rem;color:#8a7a5a;letter-spacing:.06em;text-transform:uppercase">'+p.get("tecnologias","")+'</span>'
            '<span style="color:'+c+'">'+_proj_url(p)+'</span>'
            '</div></div></div>')
    ex_html = _exp_html(v["exp"], c, "#1a1208", "#5a4a2a")
    bp = "padding:10px 22px;border:1px solid #1a1208;color:#1a1208;font-weight:500;font-size:.88rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bs = "padding:10px 22px;border:1px solid "+c+";color:"+c+";font-weight:500;font-size:.88rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bp_inv = "padding:10px 22px;border:1px solid #f5f0e8;color:#f5f0e8;font-weight:500;font-size:.88rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    btns_html = _btns(v,bp,bs); btns_inv = _btns(v,bp_inv,bs)
    card_skills = "".join('<span style="padding:3px 7px;background:rgba(255,255,255,.08);font-size:.68rem;color:rgba(245,240,232,.7)">'+s+'</span>' for s in v["skills"][:5])
    n_p,n_s = len(v["proyectos"]),len(v["skills"])
    stats_p = []
    if n_p: stats_p.append('<div><div style="font-family:DM Serif Display,serif;font-size:2rem;color:'+c+'">'+str(n_p)+'+</div><div style="font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:#8a7a5a">Proyectos</div></div>')
    if n_s: stats_p.append('<div><div style="font-family:DM Serif Display,serif;font-size:2rem;color:'+c+'">'+str(n_s)+'+</div><div style="font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:#8a7a5a">Skills</div></div>')
    stats = ('<div style="display:flex;gap:24px;margin-bottom:26px;padding-bottom:26px;border-bottom:1px solid #d4c8a8">'+"".join(stats_p)+"</div>") if stats_p else ""
    desc_short = v["desc"][:80]+"..." if len(v["desc"])>80 else v["desc"]
    proj_sec = ('<section id="proyectos"><div class="w"><h2>Proyectos</h2><div>'+projs_html+'</div></div></section>') if projs_html else ""
    skills_sec = ('<section id="skills"><div class="n"><h2>Habilidades</h2><div style="display:flex;flex-wrap:wrap;gap:8px">'+skills_html+'</div></div></section>') if skills_html else ""
    exp_sec = ('<section id="experiencia"><div class="n"><h2>Experiencia</h2><div>'+ex_html+'</div></div></section>') if ex_html else ""
    css = ("*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}"
           "body{font-family:DM Sans,sans-serif;background:#f5f0e8;color:#1a1208;line-height:1.7}a{text-decoration:none;color:inherit}"
           ".w{width:min(1100px,calc(100% - 48px));margin:0 auto}.n{width:min(780px,calc(100% - 48px));margin:0 auto}"
           "nav{position:sticky;top:0;z-index:100;background:#f5f0e8;border-bottom:2px solid #1a1208;padding:16px 0}"
           ".nav-i{display:flex;align-items:center;justify-content:space-between}"
           ".nav-logo{font-family:DM Serif Display,serif;font-size:1.2rem;color:#1a1208}"
           ".nl{display:flex;gap:28px}.nl a{color:#8a7a5a;font-size:.76rem;font-weight:500;letter-spacing:.08em;text-transform:uppercase;transition:.15s}.nl a:hover{color:#1a1208}"
           "section{padding:72px 0;border-bottom:1px solid #d4c8a8}section:last-of-type{border-bottom:none}"
           "h2{font-family:DM Serif Display,serif;font-size:2.4rem;letter-spacing:-.03em;margin-bottom:28px}"
           "footer{padding:28px 0;text-align:center;color:#8a7a5a;font-size:.76rem}"
           "@media(max-width:860px){.nl{display:none}.hg{grid-template-columns:1fr!important}}")
    return ("<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>"+v["nombre"]+" &middot; Portfolio</title>"
        "<link href=\"https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap\" rel=\"stylesheet\">"
        "<style>"+ac+css+"</style></head><body>"
        "<nav><div class=\"w nav-i\"><span class=\"nav-logo\">"+v["nombre"]+"</span>"
        "<div class=\"nl\"><a href=\"#proyectos\">Proyectos</a><a href=\"#skills\">Skills</a><a href=\"#contacto\">Contacto</a></div></div></nav>"
        "<section style=\"border-bottom:2px solid #1a1208;padding:80px 0 60px\">"
        "<div class=\"w hg\" style=\"display:grid;grid-template-columns:1fr 260px;gap:52px;align-items:start\">"
        "<div class=\"anim-el\">"
        "<p style=\"font-size:.68rem;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:#8a7a5a;margin-bottom:18px\">Portfolio &middot; "+v["rol"]+" &middot; "+str(v["anio"])+"</p>"
        "<h1 style=\"font-family:DM Serif Display,serif;font-size:clamp(4rem,7vw,7.5rem);line-height:.86;letter-spacing:-.03em;margin-bottom:22px\">"
        +nombre1+"<br><em style=\"font-style:italic;color:"+c+"\">"+nombre2+"</em></h1>"
        "<p style=\"font-family:DM Serif Display,serif;color:"+c+";font-size:1.1rem;font-style:italic;margin-bottom:18px\">"+desc_short+"</p>"
        "<p style=\"color:#5a4a2a;font-size:.92rem;max-width:520px;line-height:1.9;font-weight:300;margin-bottom:26px\">"+v["desc"]+"</p>"
        +stats+"<div style=\"display:flex;gap:10px;flex-wrap:wrap\">"+btns_html+"</div></div>"
        "<div class=\"anim-el\" style=\"animation-delay:.15s;background:#1a1208;padding:28px;color:#f5f0e8\">"
        +_avatar(v,72,"0px")+
        "<div style=\"margin-top:14px\">"
        "<span style=\"font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:#8a7a5a;display:block;margin-bottom:2px\">Nombre</span>"
        "<span style=\"font-family:DM Serif Display,serif;font-size:1rem;color:#f5f0e8;display:block;margin-bottom:12px\">"+v["nombre"]+"</span>"
        "<span style=\"font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:#8a7a5a;display:block;margin-bottom:2px\">Rol</span>"
        "<span style=\"font-family:DM Serif Display,serif;font-size:1rem;color:#f5f0e8;display:block;margin-bottom:12px\">"+v["rol"]+"</span>"
        "<span style=\"font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:#8a7a5a;display:block;margin-bottom:6px\">Skills</span>"
        "<div style=\"display:flex;flex-wrap:wrap;gap:4px\">"+card_skills+"</div>"
        "</div></div></div></section>"
        +proj_sec+skills_sec+exp_sec+
        "<section id=\"contacto\"><div class=\"n\"><div class=\"anim-el\" style=\"background:#1a1208;padding:56px;text-align:center\">"
        "<h2 style=\"color:#f5f0e8;margin-bottom:12px\">Hablamos?</h2>"
        "<p style=\"color:#8a7a5a;margin-bottom:28px\">Disponible para nuevas oportunidades y proyectos.</p>"
        "<div style=\"display:flex;gap:10px;justify-content:center;flex-wrap:wrap\">"+btns_inv+"</div>"
        "</div></div></section>"
        "<footer><div class=\"w\"><p>"+v["nombre"]+" &middot; Portfolio "+str(v["anio"])+"</p></div></footer>"
        +_ANIM_JS+"</body></html>")


def _organico(datos):
    v=_v(datos); c=v["color"]; ac=_anim_css(v["animacion"])
    skills_html = "".join('<span class="anim-el" style="padding:9px 18px;border-radius:999px;background:#fff;border:1px solid #e8d8c8;font-size:.85rem;font-weight:500;color:#5a3a1a">'+s+'</span>' for s in v["skills"])
    projs_html = ""
    for i,p in enumerate(v["proyectos"]):
        projs_html += ('<article class="anim-el" style="background:#fff;border:1px solid #e8d8c8;border-radius:20px;overflow:hidden;box-shadow:0 4px 20px rgba(180,120,60,.07);animation-delay:'+str(i*0.1)+'s">'
            +_proj_img(p,c,200)+
            '<div style="padding:20px"><h4 style="font-family:Fraunces,serif;font-size:1.05rem;font-weight:700;margin-bottom:8px;color:#2c1810">'+p.get("titulo","")+'</h4>'
            '<p style="color:#7a5a3a;font-size:.87rem;margin-bottom:12px;line-height:1.75;font-weight:300">'+p.get("descripcion","")+'</p>'
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">'
            '<span style="padding:4px 12px;border-radius:999px;background:'+c+'18;font-size:.75rem;font-weight:600;color:'+c+'">'+p.get("tecnologias","")+'</span>'
            '<span style="color:'+c+';font-size:.82rem;font-weight:600">'+_proj_url(p)+'</span>'
            '</div></div></article>')
    ex_html = _exp_html(v["exp"], c, "#2c1810", "#7a5a3a")
    bp = "padding:13px 26px;border-radius:999px;background:"+c+";color:#fff;font-weight:600;font-size:.9rem;border:none;text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    bs = "padding:13px 26px;border-radius:999px;background:transparent;color:"+c+";font-weight:600;font-size:.9rem;border:1.5px solid "+c+";text-decoration:none;display:inline-flex;align-items:center;gap:6px"
    btns_html = _btns(v,bp,bs)
    card_skills = "".join('<span style="padding:5px 12px;border-radius:999px;background:'+c+'14;font-size:.75rem;font-weight:500;color:#7a5a3a">'+s+'</span>' for s in v["skills"][:6])
    social = _social_links(v, c)
    social_row = ('<div style="margin-top:16px;padding-top:16px;border-top:1px solid #e8d8c8;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">'+social+'</div>') if social else ""
    n_p,n_s = len(v["proyectos"]),len(v["skills"])
    stats_p = []
    if n_p: stats_p.append('<div><div style="font-family:Fraunces,serif;font-size:2rem;font-weight:700;color:'+c+'">'+str(n_p)+'+</div><div style="font-size:.7rem;color:#8a6a4a;letter-spacing:.06em;text-transform:uppercase">Proyectos</div></div>')
    if n_s: stats_p.append('<div><div style="font-family:Fraunces,serif;font-size:2rem;font-weight:700;color:'+c+'">'+str(n_s)+'+</div><div style="font-size:.7rem;color:#8a6a4a;letter-spacing:.06em;text-transform:uppercase">Skills</div></div>')
    stats = ('<div style="display:flex;gap:20px;margin-bottom:26px;padding-bottom:26px;border-bottom:1px solid #e8d8c8">'+"".join(stats_p)+"</div>") if stats_p else ""
    skills_sec = ('<section id="skills" style="border-top:1px solid #e8d8c8"><div class="n"><div class="sl"><h2>Habilidades</h2></div><div style="display:flex;flex-wrap:wrap;gap:10px">'+skills_html+'</div></div></section>') if skills_html else ""
    proj_sec = ('<section id="proyectos" style="border-top:1px solid #e8d8c8"><div class="w"><div class="sl"><h2>Proyectos</h2></div><div class="pg">'+projs_html+'</div></div></section>') if projs_html else ""
    exp_sec = ('<section id="experiencia" style="border-top:1px solid #e8d8c8"><div class="n"><div class="sl"><h2>Experiencia</h2></div><div>'+ex_html+'</div></div></section>') if ex_html else ""
    css = ("*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}"
           "body{font-family:Plus Jakarta Sans,sans-serif;background:#fdf6ee;color:#2c1810;line-height:1.7}a{text-decoration:none;color:inherit}"
           ".w{width:min(1100px,calc(100% - 48px));margin:0 auto}.n{width:min(780px,calc(100% - 48px));margin:0 auto}"
           "nav{position:sticky;top:0;z-index:100;background:rgba(253,246,238,.92);backdrop-filter:blur(14px);border-bottom:1px solid #e8d8c8;padding:14px 0}"
           ".nav-i{display:flex;align-items:center;justify-content:space-between}"
           ".nav-logo{font-family:Fraunces,serif;font-size:1.15rem;color:#2c1810;font-weight:700}"
           ".nl{display:flex;gap:28px}.nl a{color:#8a6a4a;font-size:.82rem;font-weight:500;transition:.15s}.nl a:hover{color:#2c1810}"
           "section{padding:72px 0}h2{font-family:Fraunces,serif;font-size:2.1rem;font-weight:700;letter-spacing:-.03em;margin-bottom:28px}"
           ".sl{display:flex;align-items:center;gap:14px;margin-bottom:28px}.sl h2{margin:0}.sl::after{content:\'\';flex:1;height:1px;background:#e8d8c8}"
           ".pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:20px}"
           "footer{padding:28px 0;border-top:1px solid #e8d8c8;text-align:center;color:#8a6a4a;font-size:.78rem}"
           "@media(max-width:860px){.nl{display:none}.hg{grid-template-columns:1fr!important}}")
    return ("<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>"+v["nombre"]+" &middot; Portfolio</title>"
        "<link href=\"https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,700;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap\" rel=\"stylesheet\">"
        "<style>"+ac+css+"</style></head><body>"
        "<nav><div class=\"w nav-i\"><span class=\"nav-logo\">"+v["nombre"]+"</span>"
        "<div class=\"nl\"><a href=\"#proyectos\">Proyectos</a><a href=\"#skills\">Skills</a><a href=\"#contacto\">Contacto</a></div></div></nav>"
        "<section style=\"padding:100px 0 72px\">"
        "<div class=\"w hg\" style=\"display:grid;grid-template-columns:1fr 300px;gap:56px;align-items:center\">"
        "<div class=\"anim-el\">"
        "<span style=\"display:inline-flex;align-items:center;gap:5px;padding:5px 14px;border-radius:999px;"
        "background:"+c+"20;border:1px solid "+c+"40;font-size:.72rem;font-weight:600;color:"+c+";margin-bottom:20px\">Portfolio &middot; "+str(v["anio"])+"</span>"
        "<h1 style=\"font-family:Fraunces,serif;font-size:clamp(3rem,5.5vw,5.2rem);line-height:.9;letter-spacing:-.04em;font-weight:700;margin-bottom:16px\">"+v["nombre"]+"</h1>"
        "<p style=\"color:"+c+";font-size:1rem;font-weight:600;margin-bottom:16px\">"+v["rol"]+"</p>"
        "<p style=\"color:#7a5a3a;font-size:.95rem;max-width:480px;line-height:1.9;font-weight:300;margin-bottom:28px\">"+v["desc"]+"</p>"
        +stats+"<div style=\"display:flex;gap:10px;flex-wrap:wrap\">"+btns_html+"</div></div>"
        "<div class=\"anim-el\" style=\"animation-delay:.15s;background:#fff;border:1px solid #e8d8c8;border-radius:24px;padding:28px;box-shadow:0 8px 40px rgba(180,120,60,.08);text-align:center\">"
        +_avatar(v,80,"50%")+
        "<h3 style=\"font-family:Fraunces,serif;font-size:1.3rem;font-weight:700;margin:14px 0 4px;color:#2c1810\">"+v["nombre"]+"</h3>"
        "<p style=\"color:"+c+";font-size:.85rem;font-weight:600;margin-bottom:16px\">"+v["rol"]+"</p>"
        "<div style=\"display:flex;flex-wrap:wrap;gap:5px;justify-content:center\">"+card_skills+"</div>"
        +social_row+
        "</div></div></section>"
        +skills_sec+proj_sec+exp_sec+
        "<section id=\"contacto\" style=\"border-top:1px solid #e8d8c8\"><div class=\"n\">"
        "<div class=\"anim-el\" style=\"background:linear-gradient(135deg,"+c+"18,"+c+"08);border:1px solid "+c+"30;border-radius:28px;padding:56px;text-align:center\">"
        "<h2 style=\"margin-bottom:12px\">Hablamos?</h2>"
        "<p style=\"color:#7a5a3a;margin-bottom:28px;font-size:.97rem\">Siempre abierto a nuevas colaboraciones y proyectos.</p>"
        "<div style=\"display:flex;gap:12px;justify-content:center;flex-wrap:wrap\">"+btns_html+"</div>"
        "</div></div></section>"
        "<footer><div class=\"w\"><p>"+v["nombre"]+" &middot; Portify "+str(v["anio"])+"</p></div></footer>"
        +_ANIM_JS+"</body></html>")



def extract_partial_data(history):
    """
    Extrae datos del historial analizando qué preguntó la IA y qué respondió el usuario.
    Sin llamada extra a Ollama — analiza el turno a turno directamente.
    """
    result = {
        "nombre": "", "rol": "", "descripcion": "",
        "habilidades": [], "proyectos": [], "experiencia": [],
        "email": "", "redes": {"linkedin": "", "github": "", "twitter": "", "instagram": "", "youtube": "", "tiktok": "", "website": ""}
    }

    # Señales que indican qué estaba pidiendo el bot en ese turno
    BOT_SIGNALS = {
        "nombre":      ["cómo te llamas", "tu nombre", "nombre completo", "llamas?", "nombre?"],
        "rol":         ["dedicas", "estudias", "profesión", "trabajas", "qué eres", "a qué te", "rol?", "profesión?"],
        "descripcion": ["cuéntame", "sobre ti", "quién eres", "descríbete", "háblame de ti", "descripción"],
        "habilidades": ["habilidades", "tecnologías", "lenguajes", "frameworks", "herramientas", "sabes usar", "dominas", "skills"],
        "proyectos":   ["proyecto", "proyectos", "has creado", "has hecho", "desarrollado", "nombre del proyecto", "qué hace"],
        "experiencia": ["experiencia", "formación", "trabajado", "estudios", "carrera", "empresa", "has trabajado"],
        "contacto":    ["contactarte", "email", "linkedin", "github", "redes", "correo", "cómo te encuentran"],
    }

    # Patrones que el usuario puede usar espontáneamente para dar su nombre/rol
    NOMBRE_PATTERNS = [
        r"(?:me llamo|soy|mi nombre es|llámame)\s+([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ]+)*)",
    ]
    ROL_PATTERNS = [
        r"(?:soy|trabajo como|trabajo de|me dedico a|estudio)\s+(.{4,60}?)(?:\.|,|$|\sy\s)",
    ]

    def _extract_net(user_text):
        parts = re.split(r"[\s,;]+", user_text)
        net_map = [
            ("linkedin",  ["linkedin.com", "linkedin"]),
            ("github",    ["github.com", "github"]),
            ("twitter",   ["twitter.com", "x.com", "twitter"]),
            ("instagram", ["instagram.com", "instagram"]),
            ("youtube",   ["youtube.com", "youtu.be", "youtube"]),
            ("tiktok",    ["tiktok.com", "tiktok"]),
            ("website",   ["http://", "https://", "www."]),
        ]
        for net_key, patterns in net_map:
            if any(pat in user_text.lower() for pat in patterns):
                for p in parts:
                    if any(pat in p.lower() for pat in patterns):
                        result["redes"][net_key] = p
                        break

    turns = [m for m in history if isinstance(m, dict) and m.get("role") in ("user", "assistant")]

    for i, msg in enumerate(turns):
        if msg.get("role") != "assistant":
            continue
        bot_text = (msg.get("content", "") or "").lower()
        if i + 1 >= len(turns) or turns[i+1].get("role") != "user":
            continue
        user_text = (turns[i+1].get("content", "") or "").strip()
        if not user_text or len(user_text) < 2:
            continue
        user_lower = user_text.lower()
        SKIP = {"no", "ninguno", "ninguna", "no tengo", "sin experiencia", "no quiero", "nada", "ningún proyecto"}

        # Detectar qué preguntó el bot y asignar la respuesta del usuario
        matched_field = None
        for field, keywords in BOT_SIGNALS.items():
            if any(kw in bot_text for kw in keywords):
                matched_field = field
                break

        if matched_field == "nombre" and not result["nombre"]:
            result["nombre"] = user_text
        elif matched_field == "rol" and not result["rol"]:
            result["rol"] = user_text
        elif matched_field == "descripcion" and not result["descripcion"]:
            result["descripcion"] = user_text
        elif matched_field == "habilidades" and not result["habilidades"]:
            skills = [s.strip() for s in re.split(r"[,;/·•\n]+", user_text) if s.strip() and 1 < len(s.strip()) < 40]
            if skills:
                result["habilidades"] = skills
        elif matched_field == "proyectos":
            if user_lower not in SKIP:
                proj = {"titulo": user_text, "descripcion": "", "tecnologias": "", "url": "", "imagen": ""}
                # Si el bot preguntó por el nombre y el usuario dio más info, intentar parsear
                url_m = re.search(r'https?://\S+|www\.\S+', user_text)
                if url_m:
                    proj["url"] = url_m.group()
                    proj["titulo"] = user_text[:url_m.start()].strip() or user_text
                if not result["proyectos"]:
                    result["proyectos"] = [proj]
        elif matched_field == "experiencia" and not result["experiencia"]:
            if user_lower not in SKIP:
                result["experiencia"] = [{"titulo": "", "descripcion": user_text}]
        elif matched_field == "contacto":
            email_m = re.search(r"[\w.+-]+@[\w-]+\.\w+", user_text)
            if email_m:
                result["email"] = email_m.group()
            _extract_net(user_text)

        # Extraer siempre email y URLs de redes de CUALQUIER mensaje del usuario
        # (el usuario puede dar su email aunque el bot no lo haya pedido todavía)
        if not result["email"]:
            email_m = re.search(r"[\w.+-]+@[\w-]+\.\w+", user_text)
            if email_m:
                result["email"] = email_m.group()
        _extract_net(user_text)

        # Intentar extraer nombre de frases como "me llamo X" o "soy X" en CUALQUIER turno
        if not result["nombre"]:
            for pat in NOMBRE_PATTERNS:
                m = re.search(pat, user_text, re.IGNORECASE)
                if m:
                    result["nombre"] = m.group(1).strip()
                    break

        # Intentar extraer rol de frases como "soy diseñadora" o "trabajo como..."
        if not result["rol"] and matched_field not in ("nombre",):
            for pat in ROL_PATTERNS:
                m = re.search(pat, user_text, re.IGNORECASE)
                if m:
                    cand = m.group(1).strip().rstrip(".,")
                    # evitar que el nombre propio se cuele como rol
                    if cand and not re.match(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+ [A-ZÁÉÍÓÚÜÑ]', cand):
                        result["rol"] = cand
                        break

    return result

# ── EDICIÓN ──────────────────────────────────────────────────────────────────

def build_edit_prompt(datos):
    return (
        "Eres el asistente de edición de Portify. El usuario ya tiene su portfolio creado "
        "y quiere personalizarlo mediante conversación. Siempre en ESPAÑOL.\n\n"
        "PORTFOLIO ACTUAL:\n" + json.dumps(datos, ensure_ascii=False) + "\n\n"
        "COMPORTAMIENTO:\n"
        "- Si el usuario pide un cambio → aplícalo y responde con el JSON de abajo\n"
        "- Si solo comenta o pregunta → responde en español de forma natural, sin JSON\n\n"
        "CUANDO HAY CAMBIOS responde ÚNICAMENTE con este JSON (sin texto extra):\n"
        '{"actualizado":true,"mensaje":"frase corta confirmando el cambio","datos":{...portfolio completo actualizado...}}\n\n'
        "REGLAS:\n"
        "- En 'datos' incluye SIEMPRE todos los campos, no solo los modificados\n"
        "- plantilla: solo 'oscuro','minimalista','creativo','editorial','organico'\n"
        "- animacion: solo 'fade','slide-up','slide-left','zoom','float','typewriter'\n"
        "- color: valor hex como '#F18A8E'\n"
        "- habilidades: lista de strings\n"
        "- proyectos: lista de {titulo,descripcion,tecnologias,url,imagen}\n"
        "- experiencia: lista de {titulo,descripcion}"
    )

def parse_edit_response(texto):
    """Extrae JSON de edición de la respuesta de Ollama."""
    if not texto or '"actualizado"' not in texto:
        return None
    for marker in ['{"actualizado"', '{ "actualizado"']:
        idx = texto.find(marker)
        if idx == -1:
            continue
        depth = 0
        for i, ch in enumerate(texto[idx:]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(texto[idx:idx+i+1])
                    except json.JSONDecodeError:
                        break
    return None

# ── RUTAS ─────────────────────────────────────────────────────────────────
@app.route("/")
def landing_or_portfolio():
    """
    Ruta principal que maneja:
    1. Subdomínios dinámicos: juan.portify.com → muestra portfolio de Juan
    2. Dominio principal: portify.com → muestra landing page
    """
    from flask import g
    
    # Verificar si estamos en un subdominio
    if hasattr(g, 'is_portfolio_view') and g.is_portfolio_view:
        subdomain = g.subdomain_portfolio
        
        try:
            with get_db() as db:
                # Buscar portfolio por usuario_slug (subdominio)
                portfolio = db.execute(
                    "SELECT * FROM portfolios WHERE usuario_slug=?",
                    (subdomain,)
                ).fetchone()
                
                if portfolio:
                    if portfolio["html_generado"]:
                        if not _check_portfolio_access(portfolio):
                            if request.method == "POST":
                                pwd = request.form.get("pwd","")
                                if hash_pw(pwd) == portfolio["password_hash"]:
                                    session[f"portfolio_access_{portfolio['id']}"] = portfolio["password_hash"]
                                else:
                                    return _password_page(portfolio, "Contraseña incorrecta"), 403
                            else:
                                return _password_page(portfolio), 403
                        db.execute("UPDATE portfolios SET visitas = visitas + 1 WHERE usuario_slug=?", (subdomain,))
                        ua = request.headers.get("User-Agent","")
                        dev = "mobile" if any(x in ua.lower() for x in ["mobile","android","iphone","ipad"]) else "desktop"
                        ref = (request.headers.get("Referer","") or "")[:200]
                        db.execute("INSERT INTO visitas_log (portfolio_id, fecha, referrer, device_type) VALUES (?, date('now'),?,?)", (portfolio["id"], ref, dev))
                        return Response(portfolio["html_generado"], mimetype="text/html")
                    else:
                        return render_template("error.html", mensaje="Portafolio no disponible aún")
                else:
                    return render_template("error.html", mensaje=f"Portafolio '{subdomain}' no encontrado")
        except Exception as e:
            logger.error(f"Error accediendo portafolio por subdominio {subdomain}: {e}")
            return render_template("error.html", mensaje="Error al cargar el portafolio"), 500
    
    # Si no es subdominio, mostrar landing page
    return render_template("landing.html")

@app.route("/registro", methods=["GET","POST"])
def registro():
    if request.method == "POST":
        nombre=request.form.get("nombre","").strip(); email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
        if not nombre or not email or not pw: return render_template("registro.html", error="Rellena todos los campos.")
        try:
            with get_db() as db: db.execute("INSERT INTO usuarios (nombre,email,password) VALUES (?,?,?)",(nombre,email,hash_pw(pw)))
            return redirect(url_for("login"))
        except sqlite3.IntegrityError: return render_template("registro.html", error="Ese email ya está registrado.")
    return render_template("registro.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
        with get_db() as db: u=db.execute("SELECT * FROM usuarios WHERE email=? AND password=?",(email,hash_pw(pw))).fetchone()
        if u:
            session.update({"user_id":u["id"],"user_nombre":u["nombre"],"user_plan":u["plan"]}); return redirect(url_for("dashboard"))
        return render_template("login.html", error="Email o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("landing_or_portfolio"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        portfolios = db.execute("SELECT * FROM portfolios WHERE usuario_id=? ORDER BY creado_en DESC", (session["user_id"],)).fetchall()
        user       = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
        pids       = [p["id"] for p in portfolios]
        raw_sparks = get_sparklines(db, pids)
        # Unread messages per portfolio
        unread_rows = db.execute(
            "SELECT portfolio_id, COUNT(*) as cnt FROM mensajes_contacto "
            "WHERE portfolio_id IN (%s) AND leido=0 GROUP BY portfolio_id" % ",".join("?"*len(pids)),
            pids
        ).fetchall() if pids else []
    unread_msgs = {r["portfolio_id"]: r["cnt"] for r in unread_rows}
    sparklines = {pid: make_sparkline_svg(vals) for pid, vals in raw_sparks.items()}
    return render_template("dashboard.html", portfolios=portfolios, user=user,
                           plan=PLANES.get(user["plan"], PLANES["free"]),
                           domain_base=DOMAIN_BASE, sparklines=sparklines,
                           unread_msgs=unread_msgs)

@app.route("/chat")
def chat():
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        user=db.execute("SELECT * FROM usuarios WHERE id=?",(session["user_id"],)).fetchone()
        count=db.execute("SELECT COUNT(*) as c FROM portfolios WHERE usuario_id=?",(session["user_id"],)).fetchone()["c"]
    plan=PLANES.get(user["plan"],PLANES["free"])
    if count >= plan["max_portfolios"]: return redirect(url_for("planes"))
    session["chat_history"]=[]
    return render_template("chat.html", user=user)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "user_id" not in session: return jsonify({"error":"No autenticado"}),401
    # Rate limiting: máx 20 requests por minuto
    if not check_rate_limit(session["user_id"], max_requests=20, window_seconds=60):
        return jsonify({"error":"Demasiadas solicitudes. Intenta en 1 minuto."}),429
    try:
        req_data = request.get_json()
        if not isinstance(req_data, dict):
            return jsonify({"error":"Datos inválidos"}),400
        msg = (req_data.get("mensaje","") or "").strip()
        if not msg or len(msg) > 2000:
            return jsonify({"error":"Mensaje inválido o muy largo"}),400
        history = session.get("chat_history",[])
        if not history:
            history = [
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"assistant","content":"¡Hola! 👋 Soy el asistente de Portify. Voy a hacerte unas preguntas rápidas para crear tu portfolio profesional.\n\n¿Cómo te llamas?"}
            ]
        history.append({"role":"user","content":msg})
        # Inyectar estado actual para evitar preguntas repetidas
        parcial_actual = extract_partial_data(history)
        context_note = build_context_note(parcial_actual)
        history_for_model = history[:-1] + [{"role":"system","content":context_note}] + [history[-1]]
        respuesta = chat_ollama(history_for_model)
        # Validar que respuesta es string y no es un error
        if not isinstance(respuesta, str) or respuesta.startswith("⚠️"):
            logger.warning(f"Ollama error: {respuesta}")
            # Aún así guardar en historial
            history.append({"role":"assistant","content":respuesta})
            session["chat_history"] = history
            return jsonify({"respuesta":respuesta,"listo":False,"parcial":{}})
        history.append({"role":"assistant","content":respuesta})
        session["chat_history"] = history
        parsed = parse_json(respuesta)
        if parsed and parsed.get("listo"):
            logger.info(f"Portfolio completado para usuario {session['user_id']}")
            return jsonify({"respuesta":"¡Perfecto! Ya tengo todo lo que necesito. Generando tu portfolio ahora... ✨","listo":True,"datos":parsed["datos"]})
        # Limpiar JSON visible de la respuesta
        clean = _clean_response_text(respuesta)
        # Extraer datos parciales para actualizar el sidebar/preview
        parcial = extract_partial_data(history)
        return jsonify({"respuesta": clean or respuesta, "listo": False, "parcial": parcial})
    except Exception as e:
        logger.error(f"Error en api_chat: {e}")
        return jsonify({"error":"Error procesando mensaje"}),500

@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    if not check_rate_limit(session["user_id"], max_requests=20, window_seconds=60):
        return jsonify({"error": "Demasiadas solicitudes. Intenta en 1 minuto."}), 429
    try:
        req_data = request.get_json()
        if not isinstance(req_data, dict):
            return jsonify({"error": "Datos inválidos"}), 400
        msg = (req_data.get("mensaje", "") or "").strip()
        if not msg or len(msg) > 2000:
            return jsonify({"error": "Mensaje inválido o muy largo"}), 400
        history = session.get("chat_history", [])
        if not history:
            history = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "assistant", "content": "¡Hola! 👋 Soy el asistente de Portify. Voy a hacerte unas preguntas rápidas para crear tu portfolio profesional.\n\n¿Cómo te llamas?"}
            ]
        history.append({"role": "user", "content": msg})

        # Inyectar bloque de estado antes del último mensaje del usuario
        # para que el modelo sepa exactamente qué datos ya tiene
        parcial_actual = extract_partial_data(history)
        context_note = build_context_note(parcial_actual)
        # Construimos el historial que se envía al modelo:
        # system + conversación anterior + [nota de estado] + último mensaje del usuario
        history_for_model = (
            history[:-1]  # todo excepto el último mensaje del usuario
            + [{"role": "system", "content": context_note}]
            + [history[-1]]  # el mensaje del usuario
        )
        history_snap = list(history)  # guardamos el historial real (sin la nota de estado)

        def generate():
            tokens = []
            error_msg = None
            try:
                r = requests.post(
                    OLLAMA_URL,
                    json={"model": OLLAMA_MODEL, "messages": history_for_model, "stream": True},
                    stream=True, timeout=120
                )
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            tokens.append(token)
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
            except requests.exceptions.ConnectionError:
                error_msg = "⚠️ Ollama no está corriendo."
            except requests.exceptions.Timeout:
                error_msg = "⚠️ Ollama tardó demasiado. Inténtalo de nuevo."
            except Exception as e:
                error_msg = f"⚠️ Error: {str(e)}"

            if error_msg:
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
                return

            accumulated = "".join(tokens)
            full_history = history_snap + [{"role": "assistant", "content": accumulated}]
            # Update session
            session["chat_history"] = full_history
            session.modified = True

            parsed = parse_json(accumulated)
            if parsed and parsed.get("listo"):
                yield f"data: {json.dumps({'done': True, 'listo': True, 'datos': parsed['datos'], 'respuesta': '¡Perfecto! Ya tengo todo lo que necesito. Generando tu portfolio ahora... ✨'})}\n\n"
            else:
                clean = _clean_response_text(accumulated)
                parcial = extract_partial_data(full_history)
                yield f"data: {json.dumps({'done': True, 'listo': False, 'parcial': parcial, 'respuesta': clean})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    except Exception as e:
        logger.error(f"Error en api_chat_stream: {e}")
        return jsonify({"error": "Error procesando mensaje"}), 500


@app.route("/api/editar-chat/stream", methods=["POST"])
def api_editar_chat_stream():
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    if not check_rate_limit(session["user_id"], max_requests=30, window_seconds=60):
        return jsonify({"error": "Demasiadas solicitudes."}), 429
    try:
        req_data = request.get_json()
        if not isinstance(req_data, dict):
            return jsonify({"error": "Datos inválidos"}), 400
        msg = (req_data.get("mensaje", "") or "").strip()
        if not msg or len(msg) > 2000:
            return jsonify({"error": "Mensaje inválido"}), 400
        datos = req_data.get("datos", {}) or {}
        portfolio_id = req_data.get("portfolio_id")
        history = session.get("edit_history", [])
        if not history:
            history = [{"role": "system", "content": build_edit_prompt(datos)}]
        history.append({"role": "user", "content": msg})
        history_snap = list(history)

        def generate():
            tokens = []
            error_msg = None
            try:
                r = requests.post(
                    OLLAMA_URL,
                    json={"model": OLLAMA_MODEL, "messages": history_snap, "stream": True},
                    stream=True, timeout=120
                )
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            tokens.append(token)
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
            except requests.exceptions.ConnectionError:
                error_msg = "⚠️ Ollama no está corriendo."
            except Exception as e:
                error_msg = f"⚠️ Error: {str(e)}"

            if error_msg:
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
                return

            accumulated = "".join(tokens)
            full_history = history_snap + [{"role": "assistant", "content": accumulated}]
            session["edit_history"] = full_history
            session.modified = True

            parsed = parse_json(accumulated)
            if parsed and parsed.get("actualizado"):
                new_datos = parsed.get("datos", datos)
                yield f"data: {json.dumps({'done': True, 'actualizado': True, 'datos': new_datos, 'respuesta': parsed.get('mensaje','Cambio aplicado ✓')})}\n\n"
            else:
                clean = _clean_response_text(accumulated)
                yield f"data: {json.dumps({'done': True, 'actualizado': False, 'respuesta': clean})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    except Exception as e:
        logger.error(f"Error en api_editar_chat_stream: {e}")
        return jsonify({"error": "Error procesando mensaje"}), 500


@app.route("/api/editar-chat", methods=["POST"])
def api_editar_chat():
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    if not check_rate_limit(session["user_id"], max_requests=30, window_seconds=60):
        return jsonify({"error": "Demasiadas solicitudes. Intenta en 1 minuto."}), 429
    try:
        req_data = request.get_json()
        if not isinstance(req_data, dict):
            return jsonify({"error": "Datos inválidos"}), 400
        msg = (req_data.get("mensaje", "") or "").strip()
        if not msg or len(msg) > 2000:
            return jsonify({"error": "Mensaje inválido o muy largo"}), 400
        datos = req_data.get("datos", {})
        if not isinstance(datos, dict):
            datos = {}
        pid = int(req_data.get("portfolio_id", 0) or 0)

        edit_key = f"edit_history_{pid}"
        history = session.get(edit_key, [])
        if not history:
            history = [{"role": "system", "content": build_edit_prompt(datos)}]
        else:
            # Actualizar el system prompt con los datos más recientes
            history[0]["content"] = build_edit_prompt(datos)

        history.append({"role": "user", "content": msg})
        respuesta = chat_ollama(history)

        if not isinstance(respuesta, str) or respuesta.startswith("⚠️"):
            return jsonify({"respuesta": respuesta, "actualizado": False})

        history.append({"role": "assistant", "content": respuesta})
        # Limitar historial a 20 turnos para no saturar la sesión
        if len(history) > 21:
            history = [history[0]] + history[-20:]
        session[edit_key] = history

        parsed = parse_edit_response(respuesta)
        if parsed and parsed.get("actualizado") and isinstance(parsed.get("datos"), dict):
            nuevos_datos = parsed["datos"]
            mensaje = str(parsed.get("mensaje", "Portfolio actualizado."))
            if pid:
                html = generar_html(nuevos_datos)
                with get_db() as db:
                    db.execute(
                        "UPDATE portfolios SET datos=?,html_generado=?,plantilla=?,animacion=? "
                        "WHERE id=? AND usuario_id=?",
                        (json.dumps(nuevos_datos), html,
                         nuevos_datos.get("plantilla", "oscuro"),
                         nuevos_datos.get("animacion", "fade"),
                         pid, session["user_id"])
                    )
            logger.info(f"Portfolio {pid} editado por usuario {session['user_id']}")
            return jsonify({"respuesta": mensaje, "actualizado": True, "datos": nuevos_datos})

        clean = re.sub(r'```[\s\S]*?```', "", respuesta).strip()
        return jsonify({"respuesta": clean or respuesta, "actualizado": False})
    except Exception as e:
        logger.error(f"Error en api_editar_chat: {e}")
        return jsonify({"error": "Error procesando mensaje"}), 500

ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

def _save_upload(file_storage) -> tuple[str, str]:
    """Guarda el fichero en UPLOAD_FOLDER y devuelve (ruta_relativa_url, ext)."""
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_EXTS:
        raise ValueError("Formato no soportado")
    data = file_storage.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Imagen demasiado grande (máx 5 MB)")
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as fh:
        fh.write(data)
    return f"/static/uploads/{filename}", ext, data

@app.route("/api/subir-imagen", methods=["POST"])
def subir_imagen():
    """Sube una imagen y devuelve su URL en disco."""
    if "user_id" not in session: return jsonify({"error":"No autenticado"}),401
    if not check_rate_limit(session["user_id"], max_requests=30, window_seconds=60):
        return jsonify({"error":"Demasiadas solicitudes. Intenta en 1 minuto."}),429
    if "imagen" not in request.files: return jsonify({"error":"No se recibió imagen"}),400
    f = request.files["imagen"]
    if not f.filename: return jsonify({"error":"Sin archivo"}),400
    try:
        src, ext, _ = _save_upload(f)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "src": src})

@app.route("/api/analizar-imagen", methods=["POST"])
def analizar_imagen():
    """Analiza una imagen con Ollama visión y devuelve descripción + tipo detectado."""
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    # Rate limiting: máx 10 análisis por minuto
    if not check_rate_limit(session["user_id"], max_requests=10, window_seconds=60):
        return jsonify({"error":"Demasiadas solicitudes. Intenta en 1 minuto."}),429
    if "imagen" not in request.files:
        return jsonify({"error": "No se recibió imagen"}), 400

    f = request.files["imagen"]
    if not f.filename:
        return jsonify({"error": "Sin archivo"}), 400
    try:
        src, ext, imagen_bytes = _save_upload(f)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    b64 = base64.b64encode(imagen_bytes).decode()
    tipo = request.form.get("tipo", "auto")  # "perfil", "proyecto" o "auto"

    # Prompts según tipo
    if tipo == "perfil":
        prompt = (
            "Analiza esta foto de perfil profesional. "
            "Responde en español con 2-3 frases cortas: "
            "1) ¿Es adecuada como foto de perfil profesional? "
            "2) ¿Qué transmite? "
            "3) Una sugerencia de mejora si la hay. "
            "Sé directo y amable."
        )
    elif tipo == "proyecto":
        prompt = (
            "Describe brevemente esta imagen de proyecto en español. "
            "En 1-2 frases: ¿qué muestra? ¿qué tecnología o tipo de proyecto parece? "
            "Solo la descripción, sin saludos."
        )
    else:
        prompt = (
            "Mira esta imagen y determina en español: "
            "¿Es una foto de persona/perfil, una captura de pantalla de proyecto, un logo, o algo más? "
            "Luego descríbela brevemente en 2 frases. Sé directo."
        )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": [b64]
                }],
                "stream": False
            },
            timeout=60
        )
        response.raise_for_status()
        descripcion = response.json()["message"]["content"].strip()
    except Exception as e:
        descripcion = f"(No se pudo analizar la imagen: {e})"

    return jsonify({
        "ok": True,
        "src": src,
        "descripcion": descripcion,
        "tipo": tipo
    })


@app.route("/generar-preview", methods=["POST"])
def generar_preview():
    if "user_id" not in session: return "No autenticado", 401
    datos = request.get_json()
    if not isinstance(datos, dict):
        return "Datos inválidos", 400
    return generar_html(datos)

@app.route("/generar-portfolio", methods=["POST"])
def generar_portfolio():
    if "user_id" not in session: return jsonify({"error":"No autenticado"}),401
    if not check_rate_limit(session["user_id"], max_requests=10, window_seconds=60):
        return jsonify({"error":"Demasiadas solicitudes. Intenta en 1 minuto."}),429
    try:
        req_data = request.get_json()
        if not isinstance(req_data, dict):
            return jsonify({"error":"Datos inválidos"}),400
        datos = req_data.get("datos",{})
        if not isinstance(datos, dict):
            return jsonify({"error":"Datos debe ser un objeto"}),400
        if not datos.get("nombre","").strip():
            return jsonify({"error":"Nombre requerido"}),400
        for field in ["nombre", "rol", "descripcion", "email"]:
            if field in datos and isinstance(datos[field], str) and len(datos[field]) > 1000:
                return jsonify({"error":f"Campo {field} muy largo (máx 1000 caracteres)"}),400

        # Usar el agente llama3.2 para construir el portfolio sección a sección
        agent = PortfolioAgent(domain_base=DOMAIN_BASE)
        result = agent.run(datos, usuario_id=session["user_id"])

        if not result.get("ok"):
            logger.error(f"Agent error: {result.get('error')}")
            return jsonify({"error": result.get("error", "Error en el agente")}), 500

        logger.info(f"Portfolio generado por agente: usuario={session['user_id']}, id={result['portfolio_id']}, subdominio={result['subdominio_url']}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error en generar_portfolio: {e}")
        return jsonify({"error":"Error generando portfolio"}),500

@app.route("/api/actualizar-portfolio/<int:pid>", methods=["POST"])
def actualizar_portfolio(pid):
    """Regenera el portfolio con datos editados."""
    if "user_id" not in session: return jsonify({"error":"No autenticado"}),401
    req_data = request.get_json()
    if not isinstance(req_data, dict):
        return jsonify({"error":"Datos inválidos"}),400
    datos = req_data.get("datos",{})
    if not isinstance(datos, dict):
        return jsonify({"error":"Datos debe ser un objeto"}),400
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?", (pid, session["user_id"])).fetchone()
        if not p: return jsonify({"error":"No autorizado"}), 403
        # Guardar versión anterior antes de sobreescribir
        if p["datos"] and p["html_generado"]:
            db.execute(
                "INSERT INTO portfolio_versiones (portfolio_id,datos,html_generado) VALUES (?,?,?)",
                (pid, p["datos"], p["html_generado"])
            )
            # Mantener solo las últimas 10 versiones
            db.execute(
                "DELETE FROM portfolio_versiones WHERE portfolio_id=? AND id NOT IN "
                "(SELECT id FROM portfolio_versiones WHERE portfolio_id=? ORDER BY id DESC LIMIT 10)",
                (pid, pid)
            )
        canonical = f"https://{p['usuario_slug']}.{DOMAIN_BASE}" if p["usuario_slug"] else ""
        html = generar_html(datos, portfolio_id=pid)
        if canonical:
            html = _inject_head_tags(html, datos.get("nombre",""), datos.get("color","#F18A8E"), canonical)
        db.execute("UPDATE portfolios SET datos=?,html_generado=?,plantilla=?,animacion=? WHERE id=? AND usuario_id=?",
                   (json.dumps(datos),html,datos.get("plantilla","oscuro"),datos.get("animacion","fade"),pid,session["user_id"]))
    return jsonify({"ok":True})

@app.route("/portfolio/<int:pid>/versiones")
def versiones_portfolio(pid):
    if "user_id" not in session: return jsonify({"error":"No autenticado"}), 401
    with get_db() as db:
        p = db.execute("SELECT id FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
        if not p: return jsonify({"error":"No autorizado"}), 403
        vers = db.execute(
            "SELECT id, creado_en FROM portfolio_versiones WHERE portfolio_id=? ORDER BY id DESC",
            (pid,)
        ).fetchall()
    return jsonify([{"id": v["id"], "fecha": v["creado_en"]} for v in vers])

@app.route("/portfolio/<int:pid>/versiones/<int:vid>/restaurar", methods=["POST"])
def restaurar_version(pid, vid):
    if "user_id" not in session: return jsonify({"error":"No autenticado"}), 401
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
        if not p: return jsonify({"error":"No autorizado"}), 403
        v = db.execute("SELECT * FROM portfolio_versiones WHERE id=? AND portfolio_id=?",
                       (vid, pid)).fetchone()
        if not v: return jsonify({"error":"Versión no encontrada"}), 404
        # Guardar actual como nueva versión antes de restaurar
        if p["datos"] and p["html_generado"]:
            db.execute("INSERT INTO portfolio_versiones (portfolio_id,datos,html_generado) VALUES (?,?,?)",
                       (pid, p["datos"], p["html_generado"]))
        db.execute("UPDATE portfolios SET datos=?,html_generado=? WHERE id=?",
                   (v["datos"], v["html_generado"], pid))
        datos = json.loads(v["datos"])
        db.execute("UPDATE portfolios SET plantilla=?,animacion=? WHERE id=?",
                   (datos.get("plantilla","oscuro"), datos.get("animacion","fade"), pid))
    return jsonify({"ok": True})

@app.route("/portfolio-creado/<int:pid>")
def portfolio_creado(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    slug=request.args.get("slug","")
    with get_db() as db: p=db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",(pid,session["user_id"])).fetchone()
    if not p: return redirect(url_for("dashboard"))
    subdominio_url = f"https://{p['usuario_slug']}.{DOMAIN_BASE}" if p["usuario_slug"] else ""
    return render_template("portfolio_creado.html", portfolio=p, slug=slug, pid=pid,
                           subdominio_url=subdominio_url, domain_base=DOMAIN_BASE)

@app.route("/editar/<int:pid>")
def editar_portfolio(pid):
    """Editor post-generación."""
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db: p=db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",(pid,session["user_id"])).fetchone()
    if not p: return redirect(url_for("dashboard"))
    datos = {}
    if p["datos"]:
        try:
            datos = json.loads(p["datos"])
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando datos de portfolio {pid}: {e}")
            datos = {}
    return render_template("editor.html", portfolio=p, datos=datos, pid=pid,
                           animaciones=ANIMACIONES, anim_sugerida=ANIM_POR_PLANTILLA.get(p["plantilla"],"fade"))


@app.route("/portfolio/<int:pid>")
def ver_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db: p=db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",(pid,session["user_id"])).fetchone()
    if not p: return "No encontrado",404
    return p["html_generado"]

@app.route("/portfolio/<int:pid>/descargar")
def descargar_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db: p=db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",(pid,session["user_id"])).fetchone()
    if not p: return "No encontrado",404
    return Response(p["html_generado"],mimetype="text/html",headers={"Content-Disposition":f"attachment; filename=portfolio_{pid}.html"})

@app.route("/portfolio/<int:pid>/password", methods=["POST"])
def set_password(pid):
    if "user_id" not in session: return jsonify({"error":"No autenticado"}),401
    pwd = (request.get_json() or {}).get("password","").strip()
    with get_db() as db:
        if pwd:
            db.execute("UPDATE portfolios SET password_hash=? WHERE id=? AND usuario_id=?",
                       (hash_pw(pwd), pid, session["user_id"]))
        else:
            db.execute("UPDATE portfolios SET password_hash=NULL WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"]))
    return jsonify({"ok": True, "protegido": bool(pwd)})

def _check_portfolio_access(p):
    """Devuelve True si el visitante puede ver el portfolio (sin contraseña o ya autenticado)."""
    if not p["password_hash"]:
        return True
    key = f"portfolio_access_{p['id']}"
    return session.get(key) == p["password_hash"]

def _password_page(p, error=""):
    """Página de acceso con contraseña, estilada con el color del portfolio."""
    try:
        datos = json.loads(p["datos"] or "{}")
        color = datos.get("color","#7c6dfa")
        nombre = datos.get("nombre","Portfolio")
    except Exception:
        color, nombre = "#7c6dfa", "Portfolio"
    err_html = f'<p style="color:#e55;font-size:.85rem;margin-top:8px">{error}</p>' if error else ""
    return f"""<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nombre} — Acceso protegido</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#0d0d18;color:#ededf5;
     display:flex;align-items:center;justify-content:center;min-height:100vh}}
.box{{background:#13131f;border:1px solid rgba(255,255,255,.08);border-radius:20px;
      padding:44px 40px;text-align:center;width:min(380px,90vw)}}
.lock{{font-size:2.5rem;margin-bottom:16px}}
h2{{font-size:1.3rem;font-weight:600;margin-bottom:6px}}
p.sub{{color:#58586a;font-size:.85rem;margin-bottom:24px}}
input{{width:100%;padding:13px 16px;border-radius:10px;border:1px solid rgba(255,255,255,.1);
       background:rgba(255,255,255,.04);color:#ededf5;font-size:1rem;outline:none;
       text-align:center;letter-spacing:.2em;font-size:1.1rem}}
input:focus{{border-color:{color}66;box-shadow:0 0 0 3px {color}22}}
button{{margin-top:12px;width:100%;padding:13px;border-radius:10px;border:none;
        background:{color};color:#fff;font-weight:600;font-size:.95rem;cursor:pointer}}
button:hover{{filter:brightness(1.1)}}
</style></head><body>
<div class="box">
  <div class="lock">🔒</div>
  <h2>{nombre}</h2>
  <p class="sub">Este portfolio está protegido con contraseña.</p>
  <form method="POST">
    <input type="password" name="pwd" placeholder="••••••••" autofocus autocomplete="current-password">
    {err_html}
    <button type="submit">Acceder</button>
  </form>
</div></body></html>"""

@app.route("/p/<slug>", methods=["GET","POST"])
def ver_publico(slug):
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE slug=? OR custom_slug=?", (slug, slug)).fetchone()
        if not p:
            return "<h1 style='font-family:sans-serif;padding:40px;color:#888'>Portfolio no encontrado</h1>", 404
        if not _check_portfolio_access(p):
            if request.method == "POST":
                pwd = request.form.get("pwd","")
                if hash_pw(pwd) == p["password_hash"]:
                    session[f"portfolio_access_{p['id']}"] = p["password_hash"]
                else:
                    return _password_page(p, "Contraseña incorrecta"), 403
            else:
                return _password_page(p), 403
        db.execute("UPDATE portfolios SET visitas = visitas + 1 WHERE slug=?", (slug,))
        _ua = request.headers.get("User-Agent","")
        _dev = "mobile" if any(x in _ua.lower() for x in ["mobile","android","iphone","ipad"]) else "desktop"
        _ref = (request.headers.get("Referer","") or "")[:200]
        db.execute("INSERT INTO visitas_log (portfolio_id, fecha, referrer, device_type) VALUES (?, date('now'),?,?)", (p["id"], _ref, _dev))
    return p["html_generado"]

@app.route("/portfolio/<int:pid>/qr")
def qr_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT usuario_slug, slug FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
    if not p: return "No encontrado", 404
    url = (f"https://{p['usuario_slug']}.{DOMAIN_BASE}"
           if p["usuario_slug"] else f"{request.host_url}p/{p['slug']}")
    qr = qrcode.QRCode(version=1, box_size=10, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a1a", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="image/png",
                    headers={"Content-Disposition": f"attachment; filename=qr-portfolio-{pid}.png"})

# ── CONTACTO EMBEBIDO ────────────────────────────────────────────────────────
@app.route("/portfolio/<int:pid>/contactar", methods=["POST"])
def contactar_portfolio(pid):
    data = request.get_json() or {}
    nombre  = (data.get("nombre","")  or "").strip()[:100]
    email   = (data.get("email","")   or "").strip()[:200]
    mensaje = (data.get("mensaje","") or "").strip()[:2000]
    if not nombre or not email or not mensaje:
        return jsonify({"error":"Rellena todos los campos"}), 400
    if not re.match(r"[\w.+-]+@[\w-]+\.\w+", email):
        return jsonify({"error":"Email inválido"}), 400
    with get_db() as db:
        p = db.execute(
            "SELECT p.id, p.titulo, u.email AS owner_email, u.nombre AS owner_nombre "
            "FROM portfolios p JOIN usuarios u ON p.usuario_id=u.id WHERE p.id=?", (pid,)
        ).fetchone()
        if not p:
            return jsonify({"error":"Portfolio no encontrado"}), 404
        db.execute("INSERT INTO mensajes_contacto (portfolio_id,nombre,email,mensaje) VALUES (?,?,?,?)",
                   (pid, nombre, email, mensaje))
    # Notificación al dueño del portfolio
    body = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#f9f9f9;border-radius:12px;padding:28px">
      <h2 style="color:#7c6dfa;margin-bottom:4px">Nuevo mensaje en tu portfolio</h2>
      <p style="color:#555;font-size:.9rem;margin-bottom:20px">Alguien ha usado el formulario de contacto de <strong>{p['titulo']}</strong>.</p>
      <div style="background:#fff;border-radius:8px;padding:18px;border:1px solid #e5e5e5">
        <p style="margin:0 0 6px"><strong>De:</strong> {nombre} &lt;{email}&gt;</p>
        <p style="margin:0;color:#333;white-space:pre-wrap">{mensaje}</p>
      </div>
      <p style="margin-top:16px;font-size:.82rem;color:#999">
        <a href="mailto:{email}?subject=Re: tu mensaje en mi portfolio" style="color:#7c6dfa">Responder directamente →</a>
      </p>
    </div>"""
    send_email(p["owner_email"], f"Nuevo mensaje de {nombre} — Portify", body)
    return jsonify({"ok": True})

@app.route("/portfolio/<int:pid>/mensajes")
def mensajes_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT titulo FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
        if not p: return "No autorizado", 403
        msgs = db.execute(
            "SELECT * FROM mensajes_contacto WHERE portfolio_id=? ORDER BY creado_en DESC", (pid,)
        ).fetchall()
        db.execute("UPDATE mensajes_contacto SET leido=1 WHERE portfolio_id=?", (pid,))
    return render_template("mensajes.html", mensajes=msgs, titulo=p["titulo"], pid=pid)

# ── ANALYTICS ────────────────────────────────────────────────────────────────
@app.route("/portfolio/<int:pid>/stats")
def stats_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT titulo, visitas FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
        if not p: return jsonify({"error":"No autorizado"}), 403
        # Últimos 30 días
        daily = db.execute(
            "SELECT fecha, COUNT(*) as cnt FROM visitas_log WHERE portfolio_id=? "
            "AND fecha >= date('now','-29 days') GROUP BY fecha ORDER BY fecha",
            (pid,)
        ).fetchall()
        # Dispositivos
        devices = db.execute(
            "SELECT device_type, COUNT(*) as cnt FROM visitas_log WHERE portfolio_id=? "
            "AND device_type IS NOT NULL GROUP BY device_type",
            (pid,)
        ).fetchall()
        # Top referrers
        refs = db.execute(
            "SELECT referrer, COUNT(*) as cnt FROM visitas_log WHERE portfolio_id=? "
            "AND referrer IS NOT NULL AND referrer != '' "
            "GROUP BY referrer ORDER BY cnt DESC LIMIT 8",
            (pid,)
        ).fetchall()
        # Mensajes no leídos
        unread = db.execute(
            "SELECT COUNT(*) FROM mensajes_contacto WHERE portfolio_id=? AND leido=0", (pid,)
        ).fetchone()[0]
    return jsonify({
        "titulo": p["titulo"],
        "total": p["visitas"] or 0,
        "unread_msgs": unread,
        "daily": [{"fecha": r["fecha"], "cnt": r["cnt"]} for r in daily],
        "devices": [{"type": r["device_type"], "cnt": r["cnt"]} for r in devices],
        "refs":  [{"ref": r["referrer"], "cnt": r["cnt"]} for r in refs],
    })

# ── CUSTOM SLUG ───────────────────────────────────────────────────────────────
@app.route("/portfolio/<int:pid>/custom-slug", methods=["POST"])
def set_custom_slug(pid):
    if "user_id" not in session: return jsonify({"error":"No autenticado"}), 401
    data = request.get_json() or {}
    raw = (data.get("slug","") or "").strip().lower()
    slug = re.sub(r'[^a-z0-9-]', '', raw)[:50]
    if not slug or len(slug) < 2:
        return jsonify({"error":"Slug inválido (mín. 2 caracteres, solo letras, números y guiones)"}), 400
    with get_db() as db:
        p = db.execute("SELECT id FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
        if not p: return jsonify({"error":"No autorizado"}), 403
        # Check uniqueness (excluding this portfolio)
        taken = db.execute(
            "SELECT id FROM portfolios WHERE custom_slug=? AND id!=?", (slug, pid)
        ).fetchone()
        if taken:
            return jsonify({"error":"Esa URL ya está en uso, elige otra"}), 409
        db.execute("UPDATE portfolios SET custom_slug=? WHERE id=?", (slug, pid))
    return jsonify({"ok": True, "slug": slug})

@app.route("/portfolio/<int:pid>/clonar", methods=["POST"])
def clonar_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        p = db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",
                       (pid, session["user_id"])).fetchone()
        if not p: return redirect(url_for("dashboard"))
        # Check quota
        count = db.execute("SELECT COUNT(*) FROM portfolios WHERE usuario_id=?",
                           (session["user_id"],)).fetchone()[0]
        user  = db.execute("SELECT plan FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
        plan  = PLANES.get(user["plan"], PLANES["free"])
        if count >= plan["max_portfolios"]:
            return redirect(url_for("planes"))
        new_slug = uuid.uuid4().hex[:10]
        datos = p["datos"] or "{}"
        try:
            d = json.loads(datos)
            d["nombre"] = (d.get("nombre") or "Portfolio") + " (copia)"
        except Exception:
            d = {}
        db.execute(
            "INSERT INTO portfolios (usuario_id,titulo,datos,html_generado,slug,plantilla,animacion) "
            "VALUES (?,?,?,?,?,?,?)",
            (session["user_id"], (p["titulo"] or "Portfolio") + " (copia)",
             json.dumps(d), p["html_generado"] or "", new_slug,
             p["plantilla"] or "oscuro", p["animacion"] or "fade")
        )
    return redirect(url_for("dashboard"))

@app.route("/portfolio/<int:pid>/eliminar", methods=["POST"])
def eliminar_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db: db.execute("DELETE FROM portfolios WHERE id=? AND usuario_id=?",(pid,session["user_id"]))
    return redirect(url_for("dashboard"))

@app.route("/admin", methods=["GET","POST"])
def admin_panel():
    # Simple password auth via query param or form
    pwd = request.args.get("pwd") or request.form.get("pwd") or session.get("admin_auth","")
    if pwd != ADMIN_PASSWORD:
        if request.method == "POST" and request.form.get("pwd"):
            return render_template("admin.html", auth=False, error="Contraseña incorrecta")
        return render_template("admin.html", auth=False, error=None)
    session["admin_auth"] = pwd
    with get_db() as db:
        total_users    = db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        total_ports    = db.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0]
        total_visitas  = db.execute("SELECT SUM(visitas) FROM portfolios").fetchone()[0] or 0
        total_mensajes = db.execute("SELECT COUNT(*) FROM mensajes_contacto").fetchone()[0]
        total_pagos    = db.execute("SELECT COUNT(*) FROM pagos WHERE estado='completado'").fetchone()[0]
        # Last 14 days signups
        signups = db.execute(
            "SELECT DATE(creado_en) as dia, COUNT(*) as cnt FROM usuarios "
            "WHERE creado_en >= DATE('now','-13 days') GROUP BY dia ORDER BY dia"
        ).fetchall()
        # Last 14 days visits
        daily_visits = db.execute(
            "SELECT fecha, COUNT(*) as cnt FROM visitas_log "
            "WHERE fecha >= DATE('now','-13 days') GROUP BY fecha ORDER BY fecha"
        ).fetchall()
        # Plans breakdown
        planes_dist = db.execute(
            "SELECT plan, COUNT(*) as cnt FROM usuarios GROUP BY plan"
        ).fetchall()
        # Recent users
        recent_users = db.execute(
            "SELECT u.nombre, u.email, u.plan, u.creado_en, "
            "(SELECT COUNT(*) FROM portfolios WHERE usuario_id=u.id) as ports "
            "FROM usuarios u ORDER BY u.creado_en DESC LIMIT 20"
        ).fetchall()
        # Recent messages
        recent_msgs = db.execute(
            "SELECT mc.nombre, mc.email, mc.mensaje, mc.creado_en, p.titulo "
            "FROM mensajes_contacto mc JOIN portfolios p ON mc.portfolio_id=p.id "
            "ORDER BY mc.creado_en DESC LIMIT 10"
        ).fetchall()
    return render_template("admin.html", auth=True,
        total_users=total_users, total_ports=total_ports, total_visitas=total_visitas,
        total_mensajes=total_mensajes, total_pagos=total_pagos,
        signups=signups, daily_visits=daily_visits, planes_dist=planes_dist,
        recent_users=recent_users, recent_msgs=recent_msgs)

@app.route("/planes")
def planes():
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        user  = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
        pagos = db.execute("SELECT * FROM pagos WHERE usuario_id=? ORDER BY creado_en DESC LIMIT 20",
                           (session["user_id"],)).fetchall()
    return render_template("planes.html", user=user, planes=PLANES, pagos=pagos)

@app.route("/activar-plan/<plan_id>")
def activar_plan(plan_id):
    if "user_id" not in session or plan_id not in PLANES: return redirect(url_for("planes"))
    with get_db() as db: db.execute("UPDATE usuarios SET plan=? WHERE id=?",(plan_id,session["user_id"]))
    session["user_plan"]=plan_id
    return redirect(url_for("dashboard"))

@app.route("/descubrir")
def descubrir():
    with get_db() as db:
        portfolios = db.execute(
            "SELECT p.id, p.titulo, p.plantilla, p.usuario_slug, p.slug, p.visitas, p.creado_en, "
            "       u.nombre as autor_nombre, p.datos "
            "FROM portfolios p JOIN usuarios u ON p.usuario_id=u.id "
            "WHERE p.password_hash IS NULL AND p.html_generado IS NOT NULL "
            "ORDER BY p.creado_en DESC LIMIT 60"
        ).fetchall()
    items = []
    for p in portfolios:
        try:
            d = json.loads(p["datos"] or "{}")
        except Exception:
            d = {}
        items.append({
            "id": p["id"],
            "nombre": d.get("nombre", p["autor_nombre"]),
            "rol": d.get("rol", ""),
            "plantilla": p["plantilla"] or "oscuro",
            "slug": p["slug"],
            "usuario_slug": p["usuario_slug"],
            "visitas": p["visitas"] or 0,
            "color": d.get("color","#7c6dfa"),
            "creado_en": p["creado_en"][:10] if p["creado_en"] else "",
        })
    return render_template("descubrir.html", portfolios=items, domain_base=DOMAIN_BASE)

# ── CHECKOUT ──────────────────────────────────────────────────────────────────

@app.route("/sitemap.xml")
def sitemap():
    base = f"https://{DOMAIN_BASE}"
    with get_db() as db:
        portfolios = db.execute(
            "SELECT usuario_slug, slug, creado_en FROM portfolios "
            "WHERE password_hash IS NULL AND html_generado IS NOT NULL "
            "ORDER BY creado_en DESC LIMIT 500"
        ).fetchall()
    urls = [
        (base + "/",           "1.0",  "daily"),
        (base + "/descubrir",  "0.8",  "daily"),
        (base + "/login",      "0.5",  "monthly"),
        (base + "/registro",   "0.9",  "monthly"),
    ]
    for p in portfolios:
        url = f"https://{p['usuario_slug']}.{DOMAIN_BASE}" if p["usuario_slug"] else f"{base}/p/{p['slug']}"
        lastmod = p["creado_en"][:10] if p["creado_en"] else datetime.now().date().isoformat()
        urls.append((url, "0.7", "weekly", lastmod))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for entry in urls:
        loc, pri, freq = entry[0], entry[1], entry[2]
        lastmod = entry[3] if len(entry) > 3 else datetime.now().date().isoformat()
        lines.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq><priority>{pri}</priority></url>")
    lines.append("</urlset>")
    return Response("\n".join(lines), mimetype="application/xml")


@app.route("/robots.txt")
def robots():
    base = f"https://{DOMAIN_BASE}"
    txt = f"""User-agent: *
Allow: /
Allow: /descubrir
Allow: /p/
Disallow: /dashboard
Disallow: /chat
Disallow: /api/
Disallow: /admin
Disallow: /checkout/
Disallow: /editar/
Disallow: /portfolio/
Disallow: /.flask_sessions/

Sitemap: {base}/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.route("/checkout/<plan_id>", methods=["GET", "POST"])
def checkout(plan_id):
    if "user_id" not in session: return redirect(url_for("login"))
    if plan_id not in PLANES or plan_id == "free":
        return redirect(url_for("planes"))
    plan = PLANES[plan_id]
    with get_db() as db:
        user = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
    if user["plan"] == plan_id:
        return redirect(url_for("planes"))

    error = None
    if request.method == "POST":
        card_raw = request.form.get("card_number","").replace(" ","").replace("-","")

        # [STRIPE] Aquí iría: stripe.PaymentIntent.create(amount=plan["precio"]*100, currency="eur")
        if STRIPE_SECRET_KEY:
            # import stripe; stripe.api_key = STRIPE_SECRET_KEY
            # intent = stripe.PaymentIntent.create(amount=int(plan["precio"]*100), currency="eur")
            pass

        # Simulación ficticia — rechaza la tarjeta de test de fallo
        if card_raw == _CARD_DECLINE_TEST:
            error = "Tarjeta rechazada. Comprueba los datos o usa otra tarjeta."
        else:
            referencia = f"pay_{uuid.uuid4().hex[:20]}"
            with get_db() as db:
                db.execute(
                    "INSERT INTO pagos (usuario_id,plan,importe,estado,referencia,proveedor) VALUES (?,?,?,?,?,?)",
                    (session["user_id"], plan_id, plan["precio"], "completado", referencia, "ficticio")
                )
                db.execute("UPDATE usuarios SET plan=? WHERE id=?", (plan_id, session["user_id"]))
                pago_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            session["user_plan"] = plan_id
            return redirect(url_for("pago_exitoso", pago_id=pago_id))

    return render_template("checkout.html", plan=plan, plan_id=plan_id, user=user, error=error)


@app.route("/pago-exitoso/<int:pago_id>")
def pago_exitoso(pago_id):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        pago = db.execute(
            "SELECT p.*, u.nombre, u.email FROM pagos p JOIN usuarios u ON p.usuario_id=u.id "
            "WHERE p.id=? AND p.usuario_id=?", (pago_id, session["user_id"])
        ).fetchone()
    if not pago: return redirect(url_for("dashboard"))
    plan = PLANES.get(pago["plan"], {})
    return render_template("pago_exitoso.html", pago=pago, plan=plan)


@app.route("/factura/<int:pago_id>")
def factura(pago_id):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db:
        pago = db.execute(
            "SELECT p.*, u.nombre, u.email FROM pagos p JOIN usuarios u ON p.usuario_id=u.id "
            "WHERE p.id=? AND p.usuario_id=?", (pago_id, session["user_id"])
        ).fetchone()
    if not pago: return "No encontrado", 404
    plan = PLANES.get(pago["plan"], {})
    html = f"""<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><title>Factura #{pago_id:06d} — Portify</title>
<style>
  body{{font-family:Georgia,serif;max-width:680px;margin:48px auto;padding:0 24px;color:#1a1a1a}}
  .header{{display:flex;justify-content:space-between;align-items:start;border-bottom:2px solid #1a1a1a;padding-bottom:20px;margin-bottom:32px}}
  .logo{{font-size:1.6rem;font-weight:700}}
  .label{{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-bottom:4px}}
  .value{{font-size:.95rem}}
  table{{width:100%;border-collapse:collapse;margin:28px 0}}
  th{{text-align:left;border-bottom:1px solid #ddd;padding:8px 0;font-size:.78rem;text-transform:uppercase;letter-spacing:.07em;color:#888}}
  td{{padding:12px 0;border-bottom:1px solid #f0f0f0;font-size:.92rem}}
  .total-row td{{font-weight:700;font-size:1rem;border-top:2px solid #1a1a1a;border-bottom:none}}
  .footer{{margin-top:48px;font-size:.75rem;color:#aaa;border-top:1px solid #eee;padding-top:20px}}
  @media print{{body{{margin:0}}button{{display:none}}}}
</style></head><body>
<div class="header">
  <div>
    <div class="logo">Portify</div>
    <div style="font-size:.8rem;color:#888;margin-top:4px">portify.es</div>
  </div>
  <div style="text-align:right">
    <div class="label">Factura</div>
    <div class="value" style="font-size:1.1rem;font-weight:700">#{pago_id:06d}</div>
    <div style="font-size:.82rem;color:#888;margin-top:4px">{pago['creado_en'][:10]}</div>
  </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-bottom:32px">
  <div><div class="label">Facturado a</div><div class="value">{pago['nombre']}</div><div style="font-size:.82rem;color:#888">{pago['email']}</div></div>
  <div><div class="label">Referencia de pago</div><div class="value" style="font-family:monospace;font-size:.82rem">{pago['referencia']}</div></div>
</div>
<table>
  <tr><th>Descripción</th><th>Cantidad</th><th style="text-align:right">Importe</th></tr>
  <tr>
    <td>Plan {plan.get('nombre', pago['plan'].capitalize())} — Portify<br><span style="font-size:.78rem;color:#888">Suscripción mensual</span></td>
    <td>1</td>
    <td style="text-align:right">{pago['importe']:.2f} €</td>
  </tr>
  <tr class="total-row">
    <td colspan="2">Total</td>
    <td style="text-align:right">{pago['importe']:.2f} €</td>
  </tr>
</table>
<div style="margin-top:12px;font-size:.82rem;color:#666">
  Estado: <strong style="color:#22c55e">✓ Pagado</strong> · Método: {pago['metodo'].capitalize()}
</div>
<button onclick="window.print()" style="margin-top:24px;padding:10px 20px;background:#1a1a1a;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:.88rem">Imprimir / Guardar PDF</button>
<div class="footer">Portify · portify.es · Este documento es una simulación de factura.</div>
</body></html>"""
    return html


@app.route("/webhook/stripe", methods=["POST"])
def webhook_stripe():
    """
    Endpoint listo para Stripe webhooks.
    Para activar:
      1. Configura STRIPE_WEBHOOK_SECRET en el entorno.
      2. Descomenta el bloque [STRIPE] de abajo.
      3. En el dashboard de Stripe apunta el webhook a https://portify.es/webhook/stripe
    """
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature","")

    # [STRIPE]
    # import stripe
    # try:
    #     event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    # except stripe.error.SignatureVerificationError:
    #     return "", 400
    #
    # if event["type"] == "payment_intent.succeeded":
    #     intent = event["data"]["object"]
    #     # Buscar usuario por metadata y activar plan
    #     usuario_id = int(intent["metadata"].get("usuario_id", 0))
    #     plan_id    = intent["metadata"].get("plan_id", "")
    #     if usuario_id and plan_id in PLANES:
    #         with get_db() as db:
    #             db.execute("UPDATE usuarios SET plan=? WHERE id=?", (plan_id, usuario_id))
    #             db.execute("INSERT INTO pagos (usuario_id,plan,importe,estado,referencia,proveedor) VALUES (?,?,?,?,?,?)",
    #                        (usuario_id, plan_id, PLANES[plan_id]["precio"], "completado", intent["id"], "stripe"))

    logger.info(f"Webhook Stripe recibido (modo ficticio): {len(payload)} bytes")
    return "", 200


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
