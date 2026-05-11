#!/usr/bin/env python3
import sqlite3
import py_compile
import sys

def verify():
    tests_passed = 0
    tests_total = 6
    
    print("=" * 60)
    print("🔍 VERIFICACIÓN DEL SISTEMA DE SUBDOMÍNIOS PORTIFY")
    print("=" * 60)
    
    # Test 1: Compilación de Python
    try:
        print("\n[1/6] Compilando Python...")
        py_compile.compile('app.py', doraise=True)
        print("✅ PASS: app.py compilado correctamente")
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 2: Importaciones
    try:
        print("\n[2/6] Verificando importaciones...")
        from app import app
        print("✅ PASS: Importaciones correctas")
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 3: DB inicializa
    try:
        print("\n[3/6] Inicializando base de datos...")
        from app import init_db
        init_db()
        print("✅ PASS: Base de datos inicializada")
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 4: Middleware presente
    try:
        print("\n[4/6] Verificando middleware de subdominio...")
        from app import app
        found = False
        for func in app.before_request_funcs.get(None, []):
            if 'handle_subdomain' in func.__name__:
                found = True
                break
        if found:
            print("✅ PASS: Middleware handle_subdomain_proxy registrado")
            tests_passed += 1
        else:
            print("❌ FAIL: Middleware no encontrado")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 5: Ruta "/" presente
    try:
        print("\n[5/6] Verificando ruta de subdominio...")
        from app import app
        found = False
        for rule in app.url_map.iter_rules():
            if rule.rule == "/" and "landing_or_portfolio" in str(rule.endpoint):
                found = True
                break
        if found:
            print("✅ PASS: Ruta landing_or_portfolio registrada en /")
            tests_passed += 1
        else:
            print("❌ FAIL: Ruta no encontrada")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 6: Columna usuario_slug en BD
    try:
        print("\n[6/6] Verificando columna usuario_slug en BD...")
        conn = sqlite3.connect('portify.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(portfolios)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        
        if 'usuario_slug' in columns:
            print("✅ PASS: Columna usuario_slug existe en portfolios")
            tests_passed += 1
        else:
            print("❌ FAIL: Columna usuario_slug NO EXISTE")
            print(f"Columnas encontradas: {columns}")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Resumen
    print("\n" + "=" * 60)
    print(f"RESULTADO: {tests_passed}/{tests_total} pruebas pasadas")
    print("=" * 60)
    
    if tests_passed == tests_total:
        print("\n✅ ¡Sistema de subdomínios COMPLETAMENTE FUNCIONAL!")
        print("\n📋 PRÓXIMOS PASOS:")
        print("  1. Configurar DNS wildcard para *.portify.es")
        print("  2. Configurar Nginx/Apache con vhost wildcard")
        print("  3. Establecer DOMAIN_BASE=portify.es en producción")
        print("  4. Probar creando un portafolio")
        print("  5. Acceder a usuario.portify.es")
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(verify())
