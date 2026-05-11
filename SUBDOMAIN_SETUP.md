# 🌐 Configuración de Subdomínios Dinámicos para Portafolios

## Descripción

Portify ahora soporta **subdomínios dinámicos** para que cada portafolio creado sea accesible a través de su propio subdominio. Por ejemplo:

- `juan.portify.es` → Portfolio de Juan
- `maria.portify.es` → Portfolio de María  
- `carlos.portify.es` → Portfolio de Carlos

Cada usuario puede generar múltiples portafolios y cada uno tendrá su propio subdominio.

---

## Características

✅ **Acceso directo:** Los portafolios son accesibles directamente desde `usuario.dominio.com`  
✅ **Dinámico:** Se crean automáticamente al generar un portafolio  
✅ **Personalizable:** El usuario puede elegir el slug del subdominio  
✅ **Único:** No se permiten subdomínios duplicados  
✅ **Seguro:** Validación de caracteres permitidos (letras, números)  

---

## Configuración del Servidor

### 1. DNS - Registrar Wildcard Domain

Para que funcione, necesitas configurar un **wildcard DNS record**:

```dns
*.portify.es.  IN  A  192.168.1.100
portify.es.    IN  A  192.168.1.100
```

Esto redirige CUALQUIER subdominio a tu servidor principal.

### 2. Nginx - Configurar Wildcard Vhost

Crea un archivo `/etc/nginx/sites-available/portify-wildcard.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    
    # Aceptar cualquier subdominio
    server_name ~^(?<subdomain>.+)\.portify\.es$ portify.es;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Habilitar:
```bash
sudo ln -s /etc/nginx/sites-available/portify-wildcard.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Apache - Configurar Wildcard Vhost

Si usas Apache, crea `/etc/apache2/sites-available/portify-wildcard.conf`:

```apache
<VirtualHost *:80>
    ServerName portify.es
    ServerAlias *.portify.es
    
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/
</VirtualHost>
```

Habilitar:
```bash
sudo a2ensite portify-wildcard
sudo a2enmod proxy proxy_http rewrite
sudo apache2ctl configtest
sudo systemctl reload apache2
```

### 4. Variables de Entorno

Configurar en `.env` o en las variables del servidor:

```bash
# Dominio base (sin subdominio)
DOMAIN_BASE=portify.es

# O con puerto
DOMAIN_BASE=portify.local:5000
```

---

## Uso

### Generar un Portafolio con Subdominio

Cuando se crea un portafolio, automáticamente se asigna:

```json
{
  "usuario_slug": "juan",        // Basado en el nombre
  "slug": "abc1234def",           // ID único
  "url_completa": "http://juan.portify.com"
}
```

### Acceder al Portafolio

Los usuarios pueden compartir:
- **Opción 1:** `http://juan.portify.com` (más corto y amigable)
- **Opción 2:** `http://portify.com/p/abc1234def` (link tradicional)

---

## Cómo Funciona Internamente

### 1. Middleware de Detección

Cuando llega una request a `juan.portify.es`:

```python
@app.before_request
def handle_subdomain_proxy():
    # Extrae el subdominio 'juan'
    # Lo guarda en g.subdomain_portfolio
```

### 2. Ruta Proxy

Luego la ruta `/` especial de subdominio:

```python
@app.route("/")
def subdomain_portfolio():
    # Busca en BD por usuario_slug
    # Devuelve el HTML del portafolio
```

### 3. Base de Datos

En la tabla `portfolios` se almacena:

```sql
usuario_slug TEXT,     -- 'juan', 'maria', etc
slug TEXT UNIQUE,      -- ID único del portfolio
html_generado TEXT,    -- HTML a mostrar
...
```

---

## Ejemplos de Uso

### Ejemplo 1: Usuario crea portafolio

```
1. Usuario accede a portify.es/dashboard
2. Completa datos: nombre=Juan García
3. Elige plantilla y animación
4. Genera portfolio
5. Sistema crea:
   - usuario_slug: "juangarcia" (normalizado)
   - Accesible en: juan.portify.es
```

### Ejemplo 2: Compartir portafolio

```
El usuario puede:
- Compartir: "Mi portfolio está en juan.portify.es"
- Agregar a CV: https://juan.portify.es
- Usar en email: Conoce mi trabajo en juan.portify.es
```

### Ejemplo 3: Múltiples portafolios

```
Usuario "Juan" puede crear:
- juan.portify.es → Portfolio 1
- juandev.portify.es → Portfolio 2 (distinto usuario_slug)
- juan-creativo.portify.es → Portfolio 3
```

---

## Validaciones y Limitaciones

### Usuario Slug

- **Permitido:** a-z, 0-9 (minúsculas)
- **Máximo:** 20 caracteres
- **Únicos:** No se permiten duplicados
- **Fallback:** Si está vacío, usa `user{id}`

### Ejemplos de Normalización

```
"Juan García"     → "juangarcia"
"María Pérez"     → "maraperez"
"José Luis"       → "joseluis"
"123-ABC-XYZ"     → "123abcxyz"
"!!!@@@"          → "user42"  (fallback)
```

---

## Testing en Local

Para probar en localhost sin DNS:

### 1. Editar hosts

```bash
# Linux/Mac: /etc/hosts
# Windows: C:\Windows\System32\drivers\etc\hosts

127.0.0.1  portify.local
127.0.0.1  juan.portify.local
127.0.0.1  maria.portify.local
127.0.0.1  *.portify.local
```

### 2. Configurar variable

```bash
export DOMAIN_BASE=portify.local:5000
python3 app.py
```

### 3. Probar

```bash
# Landir principal
curl http://portify.local:5000/

# Portfolio específico
curl http://juan.portify.local:5000/
```

---

## Troubleshooting

### Problema: Subdominio no funciona

**Solución:**
1. Verificar DNS: `nslookup juan.portify.com`
2. Verificar nginx/apache: `sudo systemctl status nginx`
3. Verificar logs: `tail -f /var/log/nginx/error.log`
4. Verificar variable DOMAIN_BASE

### Problema: Portfolio no se muestra

**Solución:**
1. Verificar que el portafolio se generó: `SELECT * FROM portfolios`
2. Verificar el usuario_slug: `SELECT usuario_slug FROM portfolios WHERE id=?`
3. Ver logs de Flask: `DEBUG=True python3 app.py`

### Problema: Conflicto de subdomínios

**Solución:**
1. Usar UUID más largo como fallback
2. Permitir variaciones: `juan`, `juan2`, `juan-portfolio`, etc
3. Agregar timestamp: `juan-20260428`

---

## Seguridad

✅ **XSS:** Portfolio HTML se limpia antes de almacenar  
✅ **SQL Injection:** Se usan prepared statements  
✅ **Rate Limiting:** Máx 20 portfolios/minuto por usuario  
✅ **Validación:** Solo caracteres seguros en usuario_slug  
✅ **Acceso:** El HTML es público pero asociado al usuario  

---

## Futuras Mejoras

- [ ] Custom domain: usuario.ejemplo.com (en lugar de usuario.portify.com)
- [ ] Estatísticas: views, clicks por subdominio
- [ ] Analytics: Google Analytics integrado
- [ ] SSL automático: Let's Encrypt para subdomínios
- [ ] Redirecciones: forward juan.portify.com → juan-creativo.portify.com

---

## Referencia API

### POST /generar-portfolio

```json
Response:
{
  "ok": true,
  "portfolio_id": 42,
  "slug": "abc1234def",
  "usuario_slug": "juan"
}
```

### GET /

Cuando se accede a `juan.portify.com`:

```
Si existe portfolio con usuario_slug='juan':
  → Devuelve: HTML del portfolio (mimetype: text/html)

Si NO existe:
  → Devuelve: Página de error
```

---

**Versión:** 1.0  
**Fecha:** 2026-04-30  
**Autor:** GitHub Copilot
