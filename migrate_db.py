#!/usr/bin/env python3
"""
Script de migración para agregar columna usuario_slug a portfolios
"""
import sys
sys.path.insert(0, '/var/www/html/web/Web-portafolios')

import app

try:
    with app.get_db() as db:
        # Intentar agregar la columna
        db.execute("ALTER TABLE portfolios ADD COLUMN usuario_slug TEXT")
    print("✅ Columna usuario_slug agregada a la tabla portfolios")
except Exception as e:
    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
        print("✅ Columna usuario_slug ya existe")
    else:
        print(f"❌ Error: {e}")
        exit(1)

print("✅ Migración completada")
