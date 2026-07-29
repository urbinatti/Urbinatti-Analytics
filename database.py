import os
import sqlite3
from cryptography.fernet import Fernet
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

master_key = os.getenv("MASTER_KEY")
if not master_key:
    raise RuntimeError(f"Falta configurar la MASTER_KEY en el archivo .env (Buscado en: {os.path.join(BASE_DIR, '.env')})")

fernet = Fernet(master_key.encode())

def cifrar_key(api_key):
    if not api_key:
        return None
    return fernet.encrypt(api_key.encode()).decode()

def descifrar_key(api_key_cifrada):
    if not api_key_cifrada:
        return None
    try:
        return fernet.decrypt(api_key_cifrada.encode()).decode()
    except Exception as e:
        print(f"[ERROR DESCRIPTO]: {e}")
        return None

DB_PATH = os.path.join(BASE_DIR, 'analytics_urbinati.db')

def obtener_conexion():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            nombre TEXT,
            peso_kg REAL,
            altura_cm INTEGER,
            edad INTEGER,
            sexo TEXT,
            dias_entreno INTEGER,
            objetivo TEXT,
            calorias_objetivo INTEGER,
            onboarding_completado INTEGER DEFAULT 0,
            proteinas_objetivo REAL,
            grasas_objetivo REAL,
            carbs_objetivo REAL,
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
            usuario_email TEXT,
            FOREIGN KEY (usuario_email) REFERENCES usuarios(email)
        )
    ''')

    # NUEVA TABLA PARA EL HISTORIAL DE CHAT
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_email TEXT,
            rol TEXT,
            mensaje TEXT,
            timestamp DATETIME,
            FOREIGN KEY (usuario_email) REFERENCES usuarios(email)
        )
    ''')
    
    conn.commit()
    conn.close()

def obtener_usuario_por_email(email):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[ERROR OBTENER USUARIO]: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def registrar_o_actualizar_usuario_google(email, nombre):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email, onboarding_completado FROM usuarios WHERE email = ?", (email,))
        row = cursor.fetchone()
        if not row:
            cursor.execute('''
                INSERT INTO usuarios (email, nombre, onboarding_completado)
                VALUES (?, ?, 0)
            ''', (email, nombre))
            conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR GOOGLE USER]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def guardar_datos_onboarding(email, peso, altura, edad, sexo, dias_entreno, objetivo, calorias_objetivo):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE usuarios 
            SET peso_kg = ?, altura_cm = ?, edad = ?, sexo = ?, dias_entreno = ?, objetivo = ?, calorias_objetivo = ?, onboarding_completado = 1
            WHERE email = ?
        ''', (peso, altura, edad, sexo, dias_entreno, objetivo, calorias_objetivo, email))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR ONBOARDING]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def actualizar_gemini_key(email, api_key_plano):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        api_key_cifrada = cifrar_key(api_key_plano)
        cursor.execute("UPDATE usuarios SET gemini_api_key = ? WHERE email = ?", (api_key_cifrada, email))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR KEY]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()