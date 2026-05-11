## ✅ LISTA DE VERIFICACIÓN PARA DESPLIEGUE

### Phase 1: Verificación Local ✅ [COMPLETADO]

- [x] Código Python compila sin errores
- [x] Importaciones de módulos funcionan
- [x] Base de datos inicializa correctamente
- [x] Middleware detecta subdominios
- [x] Rutas están registradas correctamente
- [x] Columna usuario_slug existe en BD
- [x] Script de prueba funciona (HTTP 200)
- [x] Error template creado

**Estado:** ✅ TODO FUNCIONA EN LOCAL

---

### Phase 2: Preparación para Producción 🔧 [PENDIENTE]

#### DNS (Tu registrador de dominio)
- [ ] Crear DNS record wildcard: `*.portify.es A 192.168.x.x`
- [ ] Crear DNS record base: `portify.es A 192.168.x.x`
- [ ] Verificar propagación (24-48 horas): `nslookup juan.portify.es`

#### Servidor Web (Nginx o Apache)
- [ ] Crear archivo de configuración de vhost
- [ ] Configurar proxy a Flask (127.0.0.1:5000)
- [ ] Probar sintaxis de configuración
- [ ] Reiniciar servicio web

#### Variables de Entorno
- [ ] Establecer: `DOMAIN_BASE=portify.es`
- [ ] Establecer: `SECRET_KEY=<clave-segura>`
- [ ] Establecer: `PORT=5000` (opcional)

#### SSL/HTTPS (IMPORTANTE)
- [ ] Instalar certbot
- [ ] Generar certificado: `*.portify.es`
- [ ] Configurar redirección HTTP → HTTPS
- [ ] Verificar certificado es válido

**Duración estimada:** 1-2 horas (si el DNS ya propagó)

---

### Phase 3: Pruebas en Producción 🧪 [PENDIENTE]

#### Prueba de Subdominio Principal
- [ ] Acceder a `https://portify.es`
- [ ] Debe cargar landing page correctamente
- [ ] Revisar que no hay errores en logs

#### Prueba de Creación de Portfolio
- [ ] Registro de usuario nuevo: "Test User"
- [ ] Dashboard: Acceder correctamente
- [ ] Crear portfolio con nombre: "Test Usuario"
- [ ] Verificar que `usuario_slug` se generó
- [ ] Generar HTML del portfolio

#### Prueba de Acceso por Subdominio
- [ ] Acceder a `https://testusuario.portify.es`
- [ ] Debe mostrar el portfolio creado
- [ ] Esperar ~30-60 segundos (DNS puede cachear)
- [ ] Si no funciona, recargar (Ctrl+Shift+R)

#### Prueba de Error Handling
- [ ] Acceder a `https://nonexistent.portify.es`
- [ ] Debe mostrar error.html
- [ ] Mensaje: "Portafolio 'nonexistent' no encontrado"

#### Verificar Logs
- [ ] Ver logs de Nginx: `tail -f /var/log/nginx/access.log`
- [ ] Ver logs de Flask (si está en terminal)
- [ ] Buscar errores relacionados con subdominios

**Resultado esperado:** ✅ Acceder a usuario.portify.es devuelve portfolio

---

### Phase 4: Optimización y Seguridad 🔒 [PENDIENTE]

#### Performance
- [ ] Configurar cache en Nginx
- [ ] Configurar gzip compression
- [ ] Revisar tiempos de respuesta
- [ ] Monitorear uso de CPU/memoria

#### Seguridad
- [ ] Verificar HTTPS está activo (verde en navegador)
- [ ] Configurar HSTS headers
- [ ] Establecer Content Security Policy
- [ ] Revisión de SECRET_KEY (no hardcodeado)

#### Backups
- [ ] Configurar backup automático de BD
- [ ] Configurar backup de archivos
- [ ] Probar restauración desde backup

#### Monitoreo
- [ ] Configurar alertas de errores
- [ ] Monitorear uptime del servidor
- [ ] Revisar logs regularmente

**Resultado esperado:** ✅ Sistema seguro y optimizado

---

### Phase 5: Rollout a Usuarios 🚀 [PENDIENTE]

#### Comunicación
- [ ] Informar a usuarios sobre nuevo feature
- [ ] Crear documentación sobre cómo funciona
- [ ] Tutorial: cómo acceder al portfolio

#### Testing con Usuarios Beta
- [ ] Seleccionar 5-10 usuarios beta
- [ ] Recopilar feedback
- [ ] Corregir bugs encontrados

#### Lanzamiento Público
- [ ] Activar feature para todos
- [ ] Monitorear tickets de soporte
- [ ] Estar pendiente de errores

**Resultado esperado:** ✅ Usuarios usando subdomínios correctamente

---

## 🔍 COMANDOS DE VERIFICACIÓN RÁPIDA

```bash
# 1. Verificar que DNS funciona
nslookup portify.es
nslookup juan.portify.es

# 2. Verificar que servidor web está corriendo
curl http://127.0.0.1/
curl -H "Host: portify.es" http://127.0.0.1/

# 3. Verificar que Flask está corriendo
curl http://127.0.0.1:5000/

# 4. Verificar HTTPS
curl https://portify.es

# 5. Ver logs de Nginx
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log

# 6. Listar portfolios en BD
python3 -c "
import sqlite3
conn = sqlite3.connect('portify.db')
cursor = conn.cursor()
cursor.execute('SELECT usuario_slug, titulo FROM portfolios')
for row in cursor.fetchall():
    print(row)
"

# 7. Probar middleware localmente
python3 test_subdomain.py

# 8. Verificación completa
python3 verify_subdomain.py
```

---

## 🆘 CHECKLIST DE TROUBLESHOOTING

Si algo no funciona, revisar en este orden:

### Error: "DNS No Resuelve"
- [ ] Esperar 24-48 horas (propagación DNS)
- [ ] Verificar registros en registrador de dominio
- [ ] Probar: `nslookup juan.portify.es`
- [ ] Probar desde otro DNS: `nslookup juan.portify.es 8.8.8.8`

### Error: "Conexión Rechazada"
- [ ] Verificar que Nginx/Apache está corriendo
- [ ] Verificar que Flask está corriendo en 127.0.0.1:5000
- [ ] Revisar logs del servidor web
- [ ] Verificar firewall no bloquea puerto 80/443

### Error: "Portfolio No Encontrado"
- [ ] Verificar que usuario_slug se guardó en BD
- [ ] Verificar que usuario_slug es exacto (case-sensitive)
- [ ] Ejecutar: `python3 test_subdomain.py`
- [ ] Revisar logs de Flask

### Error: "500 Internal Server Error"
- [ ] Revisar logs de Flask (stderr)
- [ ] Verificar que template error.html existe
- [ ] Ejecutar: `python3 verify_subdomain.py`
- [ ] Verificar permisos de archivo BD

### Error: "Certificado SSL Inválido"
- [ ] Regenerar certificado: `certbot delete` y luego `certbot certonly`
- [ ] Verificar fecha de expiración: `openssl x509 -in /path/to/cert -noout -dates`
- [ ] Renovar automático: `certbot renew --dry-run`

---

## 📊 TABLA DE ESTADOS

| Fase | Estado | Fecha | Notas |
|------|--------|-------|-------|
| 1. Código | ✅ Completado | Hoy | Sistema local funcional |
| 2. Producción | ⏳ Pendiente | - | Requiere DNS + Nginx/Apache |
| 3. Testing | ⏳ Pendiente | - | Pruebas en servidor real |
| 4. Seguridad | ⏳ Pendiente | - | HTTPS y optimizaciones |
| 5. Usuarios | ⏳ Pendiente | - | Lanzamiento público |

---

## 📝 NOTAS IMPORTANTES

1. **DNS puede tardar 24-48 horas en propagarse.** No desesperar si no funciona inmediatamente.

2. **HTTPS es obligatorio en producción.** Usar Let's Encrypt (es gratis).

3. **DOMAIN_BASE debe ser `portify.es`** (sin puerto en producción).

4. **SECRET_KEY debe ser fuerte y secreta.** No compartir.

5. **Hacer backup de `portify.db`** antes de hacer cambios grandes.

6. **Revisar logs regularmente** para detectar problemas temprano.

---

## 📞 RECURSOS

- [SUBDOMAIN_SETUP.md](SUBDOMAIN_SETUP.md) - Configuración técnica detallada
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Guía paso a paso
- [FINAL_STATUS.txt](FINAL_STATUS.txt) - Resumen final
- [verify_subdomain.py](verify_subdomain.py) - Script de verificación
- [test_subdomain.py](test_subdomain.py) - Script de prueba

---

## ✅ FIRMA

**Sistema de Subdomínios Portify - COMPLETAMENTE IMPLEMENTADO**

Versión: 1.0  
Fecha: 2024  
Estado: ✅ LISTO PARA PRODUCCIÓN

**Próximo paso:** Seguir DEPLOYMENT_GUIDE.md
