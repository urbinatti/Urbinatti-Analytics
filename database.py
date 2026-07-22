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
            peso_kg REAL,
            entrenamientos_semanales INTEGER,
            objetivo TEXT,
            deficit_objetivo_kcal INTEGER,
            gemini_api_key TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros_comidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT,
            peso REAL,
            calorias REAL,
            proteinas REAL,
            carbohidratos REAL,
            grasas REAL,
            timestamp DATETIME,
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
            INSERT INTO usuarios (nombre, password_hash, peso_kg, entrenamientos_semanales, objetivo, deficit_objetivo_kcal, gemini_api_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (nombre, password_encriptada, peso, entrenamientos, objetivo, deficit, token_interno))
        conn.commit()
        return {"status": "success", "message": "Usuario registrado con éxito"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"El nombre de usuario ya existe o hubo un error: {str(e)}"}
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