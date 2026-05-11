# 🐛 Errores y Problemas Encontrados en Portify

## 1. **CRÍTICO: Base de datos sin inicializar**
**Ubicación:** `app.py` línea final
**Problema:** 
```python
if __name__ == "__main__":
    init_db()
```
El `init_db()` se llama pero nunca se ejecuta `app.run()`. Falta iniciar el servidor Flask.

**Solución:**
```python
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
```

---

## 2. **CRÍTICO: Falta el endpoint /editar/<int:pid> para GET**
**Ubicación:** `app.py` línea ~1010
**Problema:** 
```python
@app.route("/editar/<int:pid>")
def editar_portfolio(pid):
```
La ruta existe pero el archivo `editor.html` (línea ~1) probablemente no carga correctamente el script de edición. Falta JavaScript para manejar el guardado.

**Impacto:** Los usuarios no pueden editar portfolios después de crearlos.

---

## 3. **ERROR: Variable CSS indefinida en planes.html**
**Ubicación:** `templates/planes.html` línea 24
**Problema:**
```html
<span style="color:var(--muted);font-size:.85rem">{{ user.nombre }}</span>
```
La variable CSS `--muted` no está definida en `style.css`. Las variables definidas son:
- `--text`, `--text2`, `--text3` ✓
- Pero NO existe `--muted`

**Solución:** Cambiar a `var(--text3)` o `var(--text2)`

---

## 4. **ERROR: Variable CSS indefinida en planes.html línea 36**
**Ubicación:** `templates/planes.html` línea 36
**Problema:**
```html
<p>Plan actual: <strong style="color:var(--accent)">
```
La variable `--accent` NO está definida en `style.css`.

**Solución:** Cambiar a `var(--violet)` o `var(--pink)`

---

## 5. **ADVERTENCIA: XSS - HTML sin escapar en _oscuro() y otras plantillas**
**Ubicación:** `app.py` líneas 350-800 (en todas las funciones de plantillas)
**Problema:**
```python
"<h1>"+nombre1+"</h1>"  # ← Sin escapar HTML
```
Si `nombre1` contiene `<script>` o caracteres especiales, puede causar inyecciones.

**Solución:**
```python
from markupsafe import escape
"<h1>"+escape(nombre1)+"</h1>"
```

---

## 6. **ERROR: Campo 'email' no definido en variable de estilo**
**Ubicación:** `templates/planes.html` línea 38
**Problema:**
```html
<span style="color:var(--muted);
```
Más instancias de `--muted` que no existen.

---

## 7. **ADVERTENCIA: Falta validación de entrada en /generar-portfolio**
**Ubicación:** `app.py` línea ~1010
**Problema:** 
```python
def generar_portfolio():
    datos=request.get_json().get("datos",{})
```
No valida:
- Que `datos` sea un dict válido
- Límites de longitud de texto
- Caracteres inválidos

**Riesgo:** inyecciones, desbordamiento de datos.

---

## 8. **ERROR: Falta manejo de errores en chat_ollama()**
**Ubicación:** `app.py` línea ~180
**Problema:**
```python
def chat_ollama(messages):
    try:
        r = requests.post(...)
```
Está bien, pero en `/api/chat` no se valida si Ollama respondió correctamente:
```python
respuesta=chat_ollama(history)  # ← Puede ser un error, no se valida
```

**Solución:** Verificar que respuesta no sea un string de error.

---

## 9. **BUG: Función parse_json() demasiado compleja**
**Ubicación:** `app.py` líneas 210-240
**Problema:** Intenta 4 métodos diferentes para parsear JSON. Si falla, devuelve `None` sin logging.

**Impacto:** Difícil debuggear si el parsing falla.

---

## 10. **ADVERTENCIA: Contraseña débil en app.secret_key**
**Ubicación:** `app.py` línea 7
**Problema:**
```python
app.secret_key = "portify_cambia_esto_en_produccion"
```
**En producción, esto debe ser una clave fuerte y aleatoria.** No usar esta en prod.

---

## 11. **FALTA: No hay límite de rate-limiting en /api/chat**
**Ubicación:** `app.py` línea ~950
**Problema:** 
```python
@app.route("/api/chat", methods=["POST"])
def api_chat():
```
Sin protección contra spam/DoS. Cualquiera puede llamar a Ollama infinitamente.

**Solución:** Implementar Flask-Limiter.

---

## 12. **FALTA: No hay manejo de sesiones expiradas**
**Ubicación:** Todos los endpoints con `if "user_id" not in session`
**Problema:** Si la sesión expira, redirige a login pero no muestra mensaje claro.

---

## 13. **BUG: Campo "imagen" falta en base de datos**
**Ubicación:** `app.py` línea 60 (CREATE TABLE portfolios)
**Problema:**
```sql
CREATE TABLE IF NOT EXISTS portfolios (
    ...
    plantilla TEXT DEFAULT 'oscuro',
    animacion TEXT DEFAULT 'fade',
    ...
)
```
Pero en `_v()` se busca `datos.get("foto_perfil","")`. 

¿Dónde se guarda `foto_perfil`? Falta documentación o migración.

---

## 14. **ADVERTENCIA: URL sin validación en _proj_url()**
**Ubicación:** `app.py` línea ~280
**Problema:**
```python
if url and url not in ["#","ninguna","none",""]:
    if not url.startswith("http"): url = "https://"+url
```
Se agrega `https://` pero:
1. ¿Y si ya tiene `http://`?
2. No valida que sea URL válida
3. Puede generar URLs rotas

---

## 15. **CRÍTICO: Falta la ruta /p/<slug> devuelve HTML crudo**
**Ubicación:** `app.py` línea ~1040
**Problema:**
```python
@app.route("/p/<slug>")
def ver_publico(slug):
    ...
    return p["html_generado"]
```
No tiene `Content-Type: text/html`. Flask debería agregarlo automáticamente, pero es mejor ser explícito:

**Solución:**
```python
from flask import Response
return Response(p["html_generado"], mimetype="text/html")
```

---

## 16. **BUG: Portfolio no validado en editar**
**Ubicación:** `app.py` línea ~1000
**Problema:**
```python
@app.route("/editar/<int:pid>")
def editar_portfolio(pid):
    if "user_id" not in session: return redirect(url_for("login"))
    with get_db() as db: p=db.execute("SELECT * FROM portfolios WHERE id=? AND usuario_id=?",(pid,session["user_id"])).fetchone()
    if not p: return redirect(url_for("dashboard"))
    datos = json.loads(p["datos"]) if p["datos"] else {}
```
Si `p["datos"]` es NULL o JSON inválido, `json.loads()` falla sin try/except.

---

## 17. **FALTA: No hay validación de tipos en extract_partial_data()**
**Ubicación:** `app.py` línea ~830
**Problema:**
```python
for i,msg in enumerate(turns):
    ...
    bot_text = msg["content"].lower()
```
Si `msg["content"]` no es string, falla.

---

## 18. **ADVERTENCIA: Tamaño máximo de upload muy bajo**
**Ubicación:** `app.py` línea 9
**Problema:**
```python
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB
```
Para imágenes de proyectos está bien, pero no lo documenta.

---

## 19. **BUG: La función _anim_css() tiene espacios faltantes**
**Ubicación:** `app.py` línea 305
**Problema:**
```python
"@keyframes _fIn{from{opacity:0}to{opacity:1}}"
```
Le faltan espacios entre declaraciones CSS. Aunque funciona, es difícil de leer.

---

## 20. **FALTA: No hay logging**
**Todo el proyecto**
**Problema:** Sin `import logging` ni `logger.info()`. Si algo falla, no hay registro.

---

## 21. **BUG: Función _ini() puede fallar**
**Ubicación:** `app.py` línea 245
**Problema:**
```python
def _ini(nombre):
    p = nombre.strip().split()
    return (p[0][0]+p[-1][0]).upper() if len(p)>=2 else (nombre[0].upper() if nombre else "P")
```
Si `nombre` es vacío o solo espacios:
- `nombre.strip()` → ""
- `""[0]` → IndexError

**Solución:**
```python
def _ini(nombre):
    if not nombre: return "P"
    p = nombre.strip().split()
    if len(p) >= 2:
        return (p[0][0] + p[-1][0]).upper()
    return nombre.strip()[0].upper() if nombre.strip() else "P"
```

---

## 22. **FALTA: Manejo de excepciones en subir_imagen()**
**Ubicación:** `app.py` línea ~930
**Problema:**
```python
def subir_imagen():
    ...
    ext = f.filename.rsplit(".",1)[-1].lower()
```
Si `filename` no tiene punto (ej: "imagen"), falla.

---

## 23. **ADVERTENCIA: CORS no configurado**
**Ubicación:** Falta en `app.py`
**Problema:** Si hay frontend en otro dominio, las peticiones CORS fallan.

---

## 24. **FALTA: Ruta /admin inexistente**
**Ubicación:** Sin endpoint de administración
**Problema:** No hay forma de:
- Ver estadísticas
- Eliminar usuarios
- Ver errores

---

## 25. **BUG: Variable en app.py sin inicializar**
**Ubicación:** `app.py` línea ~950
**Problema:**
```python
if not history:
    history=[
        {"role":"system","content":SYSTEM_PROMPT},
        ...
    ]
history.append({"role":"user","content":msg})
```
Bien hecho, pero luego se modifica `session["chat_history"]`. ¿Qué si hay race conditions?

---

## Resumen de Severidad

| Severidad | Cantidad | Ejemplos |
|-----------|----------|----------|
| 🔴 Crítico | 4 | init_db sin run(), XSS, parse_json sin manejo, type errors |
| 🟠 Alto | 8 | CSS variables faltantes, validaciones faltantes, rate limiting |
| 🟡 Medio | 8 | Logging faltante, CORS, _ini() error handling |
| 🟢 Bajo | 5 | Documentación, comentarios, mejoras menores |

---

## Recomendaciones Inmediatas

1. ✅ Agregar `app.run()` en main
2. ✅ Escapar HTML en todas las plantillas (usar `markupsafe.escape`)
3. ✅ Verificar y arreglar variables CSS
4. ✅ Agregar validación en entrada de datos
5. ✅ Implementar logging básico
6. ✅ Agregar try/except en json.loads()
7. ✅ Mejorar _ini() para evitar IndexError
