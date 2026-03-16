from flask import Flask, render_template, request

app = Flask(__name__)


def generar_portfolio(prompt, nombre="Tu Nombre"):
    prompt_lower = prompt.lower()

    estilo = "profesional"
    tema = "claro"
    color_fondo = "#fffdf9"
    color_texto = "#111111"
    color_acento = "#ff6b2c"

    if "oscuro" in prompt_lower:
        tema = "oscuro"
        color_fondo = "#0f0f12"
        color_texto = "#f5f5f5"

    if "minimalista" in prompt_lower:
        estilo = "minimalista"
    elif "moderno" in prompt_lower:
        estilo = "moderno"
    elif "creativo" in prompt_lower:
        estilo = "creativo"

    secciones = []

    if "sobre mí" in prompt_lower or "sobre mi" in prompt_lower:
        secciones.append("Sobre mí")
    if "proyectos" in prompt_lower:
        secciones.append("Proyectos")
    if "habilidades" in prompt_lower or "skills" in prompt_lower:
        secciones.append("Habilidades")
    if "contacto" in prompt_lower:
        secciones.append("Contacto")
    if "experiencia" in prompt_lower:
        secciones.append("Experiencia")

    if not secciones:
        secciones = ["Sobre mí", "Proyectos", "Habilidades", "Contacto"]

    subtitulo = "Desarrollador web y creador digital"
    if "frontend" in prompt_lower:
        subtitulo = "Frontend Developer"
    elif "backend" in prompt_lower:
        subtitulo = "Backend Developer"
    elif "full stack" in prompt_lower or "fullstack" in prompt_lower:
        subtitulo = "Full Stack Developer"
    elif "diseñador" in prompt_lower:
        subtitulo = "Diseñador y creador visual"

    proyectos = [
        {
            "titulo": "Proyecto Uno",
            "descripcion": "Aplicación moderna con diseño limpio y experiencia intuitiva.",
            "tecnologias": "HTML, CSS, JavaScript"
        },
        {
            "titulo": "Proyecto Dos",
            "descripcion": "Sistema web enfocado en rendimiento, organización y usabilidad.",
            "tecnologias": "Python, Flask, SQLite"
        },
        {
            "titulo": "Proyecto Tres",
            "descripcion": "Portfolio visual optimizado para mostrar trabajos y habilidades.",
            "tecnologias": "Responsive Design, UI/UX"
        }
    ]

    habilidades = ["HTML", "CSS", "JavaScript", "Python", "Flask", "SQLite"]

    return {
        "nombre": nombre,
        "titulo": f"{nombre} Portfolio",
        "hero_nombre": nombre,
        "subtitulo": subtitulo,
        "descripcion": prompt,
        "estilo": estilo,
        "tema": tema,
        "color_fondo": color_fondo,
        "color_texto": color_texto,
        "color_acento": color_acento,
        "secciones": secciones,
        "proyectos": proyectos,
        "habilidades": habilidades
    }


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/generator")
def generator():
    return render_template("generator.html")


@app.route("/generar", methods=["POST"])
def generar():
    nombre = request.form.get("nombre", "Tu Nombre").strip()
    prompt = request.form.get("prompt", "").strip()

    if not prompt:
        return render_template("generator.html", error="Debes escribir una descripción.")

    portfolio = generar_portfolio(prompt, nombre)
    return render_template("preview.html", portfolio=portfolio)


if __name__ == "__main__":
    app.run(debug=True)
