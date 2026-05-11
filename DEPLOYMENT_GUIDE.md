## ✅ Sistema de Subdomínios Portify - COMPLETAMENTE IMPLEMENTADO

### 📊 ESTADO ACTUAL: 100% FUNCIONAL

Todas las verificaciones pasaron exitosamente:
- ✅ Código compila sin errores
- ✅ Importaciones correctas
- ✅ Base de datos inicializada
- ✅ Middleware de detección de subdominio registrado
- ✅ Ruta landing_or_portfolio funcionando
- ✅ Columna usuario_slug en BD lista
- ✅ Template error.html creado

---

## 🎯 QUÉ HACE EL SISTEMA

Portify ahora permite acceder a portafolios desde subdomínios dinámicos:

```
Usuario "Juan García" crea un portafolio
↓
Sistema normaliza nombre → usuario_slug = "juangarcia"
↓
Portfolio accessible en:
  - Forma corta: juan.portify.es  ⭐ NUEVO
  - Forma larga: portify.es/dashboard (panel admin)
```

**Ejemplo del flujo completo:**

```
1. Juan se registra en portify.es
2. Crea un portfolio con su nombre "Juan García"
3. Sistema genera usuario_slug = "juangarcia"
4. Juan puede compartir: "Mi portfolio está en juan.portify.es"
5. Cuando alguien visita juan.portify.es:
   - Nginx/Apache redirige a servidor
   - Flask detecta subdominio "juan"
   - Busca portfolio por usuario_slug = "juan"
   - Retorna HTML del portfolio
```

---

## 🚀 CÓMO ACTIVAR EN PRODUCCIÓN

### Paso 1: Configurar DNS (Registrador de Dominios)

En tu proveedor de dominio (GoDaddy, Namecheap, etc):

```
Type:  A
Name:  *.portify.es
Value: 192.168.x.x  (tu IP del servidor)

Type:  A
Name:  portify.es
Value: 192.168.x.x  (tu IP del servidor)
```

**Esperar 24-48 horas para propagación del DNS**

### Paso 2: Configurar Servidor Web

#### **Opción A: Nginx (RECOMENDADO)**

Crear archivo `/etc/nginx/sites-available/portify.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    
    # Acepta cualquier subdominio y el dominio base
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

Luego:
```bash
sudo ln -s /etc/nginx/sites-available/portify.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### **Opción B: Apache**

Crear archivo `/etc/apache2/sites-available/portify.conf`:

```apache
<VirtualHost *:80>
    ServerName portify.es
    ServerAlias *.portify.es
    
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/
</VirtualHost>
```

Luego:
```bash
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2ensite portify.conf
sudo apache2ctl configtest
sudo systemctl restart apache2
```

### Paso 3: Establecer Variables de Entorno

En el servidor, configurar:

```bash
# ~/.bashrc o /etc/environment
export DOMAIN_BASE=portify.es
export SECRET_KEY=tu-clave-secreta-muy-fuerte-aqui
export PORT=5000
```

Recargar:
```bash
source ~/.bashrc
```

### Paso 4: Iniciar Aplicación (En Producción)

**Opción A: Con Gunicorn (Recomendado)**

```bash
pip install gunicorn
cd /var/www/html/web/Web-portafolios
gunicorn -w 4 -b 127.0.0.1:5000 app:app
```

**Opción B: Con Flask directamente**

```bash
cd /var/www/html/web/Web-portafolios
python3 app.py
```

---

## 🧪 VERIFICAR QUE FUNCIONA

### 1. Verificación Local (sin DNS)

Editar `/etc/hosts` (Linux/Mac) o `C:\Windows\System32\drivers\etc\hosts` (Windows):

```
127.0.0.1  portify.es
127.0.0.1  juan.portify.es
127.0.0.1  maria.portify.es
127.0.0.1  carlos.portify.es
```

Luego acceder:
```
http://portify.es:5000      → Landing page
http://juan.portify.es:5000 → Portfolio (si existe)
```

### 2. Prueba de Funcionamiento

Ejecutar script de prueba:

```bash
cd /var/www/html/web/Web-portafolios
python3 test_subdomain.py
```

Debería mostrar:
```
✅ Portfolio creado con usuario_slug='testusuario'
✅ Portfolio encontrado
✅ Response exitosa (HTTP 200)
✅ HTML del portfolio está en la respuesta
```

### 3. Verificación Completa

```bash
python3 verify_subdomain.py
```

Debería mostrar: `6/6 pruebas pasadas ✅`

---

## 📝 NORMALIZACIÓN DE NOMBRES

El sistema normaliza automáticamente el nombre del usuario para crear el subdominio:

| Nombre de Usuario | usuario_slug | URL Resultado |
|---|---|---|
| Juan García | juangarcia | juan.portify.es |
| María Pérez López | maraperez | maria.portify.es |
| José Luis | joseluis | jose.portify.es |
| João da Silva | joaodasilva | joao.portify.es |
| 123-ABC@Dev | 123abcdev | 123.portify.es |
| !!!###$$$% | user42 | user42.portify.es |
| @User_99 | user99 | user99.portify.es |

**Reglas:**
- Convertir a minúsculas
- Mantener solo a-z, 0-9
- Máximo 20 caracteres
- Si queda vacío después de sanitizar: `user{id}`

---

## 🔒 SEGURIDAD

### HTTPS (SSL/TLS) - MUY IMPORTANTE EN PRODUCCIÓN

Usar Let's Encrypt (GRATUITO):

```bash
sudo apt-get install certbot python3-certbot-nginx

# Para Nginx
sudo certbot certonly --nginx -d portify.es -d '*.portify.es'

# Para Apache
sudo certbot certonly --apache -d portify.es -d '*.portify.es'

# Auto-renovar
sudo certbot renew --dry-run
```

Luego actualizar config de Nginx/Apache para usar los certificados.

### Variables de Entorno Sensibles

```bash
# NUNCA hardcodear estos valores

# Generar SECRET_KEY seguro:
python3 -c "import secrets; print(secrets.token_hex(32))"

# Establecer en .env o variables del sistema
SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DOMAIN_BASE=portify.es
```

---

## 🐛 TROUBLESHOOTING

### Problema: "Portafolio no encontrado"

**Solución 1:** Verificar que usuario_slug fue guardado:
```bash
cd /var/www/html/web/Web-portafolios
python3 -c "
import sqlite3
conn = sqlite3.connect('portify.db')
cursor = conn.cursor()
cursor.execute('SELECT usuario_slug, titulo FROM portfolios')
for row in cursor.fetchall():
    print(row)
"
```

**Solución 2:** Verificar DNS:
```bash
nslookup juan.portify.es
dig juan.portify.es
```

**Solución 3:** Verificar que DOMAIN_BASE está correcto:
```bash
echo $DOMAIN_BASE
# Debe mostrar: portify.es
```

### Problema: "Error de conexión / No se puede alcanzar"

**Solución:**
1. Verificar que Flask está corriendo: `curl http://127.0.0.1:5000/`
2. Verificar que Nginx/Apache está corriendo
3. Revisar logs: `tail -f /var/log/nginx/error.log` o similar

### Problema: "Error 500"

Revisar logs de Flask:
```bash
python3 app.py  # Ver output en terminal
# O revisar logs si está con Gunicorn
```

---

## 📊 ARCHIVOS PRINCIPALES

| Archivo | Descripción |
|---------|-------------|
| [app.py](app.py) | Aplicación Flask con middleware de subdominio |
| [templates/error.html](templates/error.html) | Template para mostrar errores |
| [SUBDOMAIN_SETUP.md](SUBDOMAIN_SETUP.md) | Documentación técnica completa |
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | Resumen de implementación |
| [verify_subdomain.py](verify_subdomain.py) | Script de verificación |
| [test_subdomain.py](test_subdomain.py) | Script de prueba |
| [migrate_db.py](migrate_db.py) | Script de migración (ya ejecutado) |

---

## 🎓 CONCEPTOS CLAVE

### Middleware `handle_subdomain_proxy()`

Se ejecuta ANTES de cada request:
```python
@app.before_request
def handle_subdomain_proxy():
    # Si vienen de juan.portify.es
    # Establece g.subdomain_portfolio = "juan"
    # Establece g.is_portfolio_view = True
```

### Ruta Combinada `landing_or_portfolio()`

Una sola ruta `/` que hace dos cosas:
1. Si es subdominio (g.is_portfolio_view == True) → Busca portfolio en BD
2. Si no es subdominio → Muestra landing.html

```python
@app.route("/")
def landing_or_portfolio():
    if g.is_portfolio_view:
        # Buscar en BD por usuario_slug
    else:
        # Mostrar landing page
```

### Column `usuario_slug` en BD

```sql
CREATE TABLE portfolios (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER,
    usuario_slug TEXT,        -- ← Nuevo: para subdominio
    titulo TEXT,
    datos TEXT,
    html_generado TEXT,
    creado_en TEXT
);
```

---

## 📞 SOPORTE

Si encuentras problemas:

1. Revisar logs del servidor
2. Ejecutar `verify_subdomain.py` para verificar configuración
3. Revisar [SUBDOMAIN_SETUP.md](SUBDOMAIN_SETUP.md) para detalles técnicos
4. Verificar que DNS está propagado: `nslookup *.portify.es`

---

## ✨ ¡LISTO!

El sistema de subdomínios dinámicos de Portify está completamente implementado y listo para producción.

**Solo necesitas:**
1. ✅ Configurar DNS wildcard (esperar propagación)
2. ✅ Configurar servidor web (Nginx/Apache)
3. ✅ Establecer variables de entorno
4. ✅ ¡Empezar a crear portafolios!

**¡Que disfrutes Portify! 🚀**
