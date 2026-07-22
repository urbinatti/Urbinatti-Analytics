import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'analytics_urbinati.db')

def obtener_conexion():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            peso REAL,
            entrenamientos INTEGER,
            objetivo TEXT,
            deficit INTEGER,
            gemini_api_key TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_comidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion_alimento TEXT,
            peso_g REAL,
            calorias REAL,
            proteinas_g REAL,
            carbohidratos_g REAL,
            grasas_g REAL,
            es_milanesa INTEGER,
            fecha_hora DATETIME,
            usuario_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_entrenamientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_entrenamiento TEXT,
            duracion_minutos INTEGER,
            calorias_quemadas_estimadas INTEGER,
            detalles_sesion TEXT,
            fecha_hora DATETIME,
            usuario_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def registrar_nuevo_usuario(nombre, password, peso, entrenamientos, objetivo, deficit):
    conn = obtener_conexion()
    cursor = conn.cursor()
    password_encriptada = generate_password_hash(password)
    token_interno = f"fit_live_{secrets.token_hex(16)}"
    
    try:
        cursor.execute('''
            INSERT INTO usuarios (nombre, password_hash, peso, entrenamientos, objetivo, deficit, gemini_api_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (nombre, password_encriptada, peso, entrenamientos, objetivo, deficit, token_interno))
        conn.commit()
        return {"success": True, "message": "Usuario registrado con éxito"}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"El nombre de usuario ya existe o hubo un error: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

def verificar_credenciales(nombre, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, nombre, password_hash, gemini_api_key FROM usuarios WHERE nombre = ?", (nombre,))
        row = cursor.fetchone()
        if row:
            usuario = dict(row)
            if check_password_hash(usuario['password_hash'], password):
                return usuario
        return None
    except Exception as e:
        print(f"[ERROR LOGIN]: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def actualizar_gemini_key(usuario_id, api_key_real):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE usuarios SET gemini_api_key = ? WHERE id = ?", (api_key_real, usuario_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR KEY]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def insertar_alimento(alimento, calorias, proteinas, carbohidratos, grasas, es_milanesa, usuario_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO registro_comidas (descripcion_alimento, peso_g, calorias, proteinas_g, carbohidratos_g, grasas_g, es_milanesa, fecha_hora, usuario_id)
            VALUES (?, 100.0, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
        ''', (alimento, calorias, proteinas, carbohidratos, grasas, es_milanesa, usuario_id))
        conn.commit()
    except Exception as e:
        print(f"[ERROR ALIMENTO]: {e}")
    finally:
        cursor.close()
        conn.close()

def insertar_entrenamiento(grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg, usuario_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        detalles = f"Ejercicio: {ejercicio_clave}. Series: {series}, Reps: {repeticiones}, Peso: {carga_kg}kg."
        cursor.execute('''
            INSERT INTO registro_entrenamientos (tipo_entrenamiento, duracion_minutos, calorias_quemadas_estimadas, detalles_sesion, fecha_hora, usuario_id)
            VALUES (?, 60, ?, ?, datetime('now', 'localtime'), ?)
        ''', (grupo_muscular, int(carga_kg * 4), detalles, usuario_id))
        conn.commit()
    except Exception as e:
        print(f"[ERROR ENTRENAMIENTO]: {e}")
    finally:
        cursor.close()
        conn.close()

def vaciar_registro_del_dia(usuario_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM registro_comidas WHERE usuario_id = ? AND date(fecha_hora) = date('now', 'localtime')", (usuario_id,))
        conn.commit()
        return "Éxito: Todo el historial de alimentación de hoy fue eliminado correctamente."
    except Exception as e:
        return f"Fallo al borrar: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def obtener_metricas_globales(usuario_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cal_hoy, prot_hoy, carb_hoy, gras_hoy = 0.0, 0.0, 0.0, 0.0
    ultimos_alimentos = []
    ultimos_entrenamientos = []
    
    try:
        cursor.execute('''
            SELECT SUM(calorias), SUM(proteinas_g), SUM(carbohidratos_g), SUM(grasas_g)
            FROM registro_comidas 
            WHERE usuario_id = ? AND date(fecha_hora) = date('now', 'localtime')
        ''', (usuario_id,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            cal_hoy, prot_hoy, carb_hoy, gras_hoy = row[0], row[1], row[2], row[3]
            
        cursor.execute('''
            SELECT descripcion_alimento as alimento, proteinas_g as prot, carbohidratos_g as carb, grasas_g as grasa, calorias 
            FROM registro_comidas WHERE usuario_id = ? ORDER BY id DESC LIMIT 5
        ''', (usuario_id,))
        ultimos_alimentos = [dict(row) for row in cursor.fetchall()]

        cursor.execute('''
            SELECT tipo_entrenamiento as grupo, detalles_sesion as ejercicio 
            FROM registro_entrenamientos WHERE usuario_id = ? ORDER BY id DESC LIMIT 5
        ''', (usuario_id,))
        ultimos_entrenamientos = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR METRICAS]: {e}")
    finally:
        cursor.close()
        conn.close()
        
    return {
        "calorias_hoy": round(float(cal_hoy or 0), 1),
        "proteinas_hoy": round(float(prot_hoy or 0), 1),
        "carbohidratos_hoy": round(float(carb_hoy or 0), 1),
        "grasas_hoy": round(float(gras_hoy or 0), 1),
        "ultimos_alimentos": ultimos_alimentos,
        "ultimos_entrenamientos": ultimos_entrenamientos
    }

def obtener_datos_atleta(usuario_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT peso, entrenamientos, objetivo, deficit FROM usuarios WHERE id = ?", (usuario_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {'peso': 70.0, 'entrenamientos': 5, 'objetivo': 'definicion', 'deficit': -500}
    except Exception as e:
        print(f"[ERROR ATLETA]: {e}")
        return {'peso': 70.0, 'entrenamientos': 5, 'objetivo': 'definicion', 'deficit': -500}
    finally:
        cursor.close()
        conn.close()