# =============================================================================
# MOTOR DE BASE DE DATOS RELACIONAL (MYSQL) - SOPORTE MULTIUSUARIO REAL
# PROYECTO: ANALYTICS DASHBOARD - JOAQUÍN URBINATTI
# =============================================================================
import os
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# Configuración de conexión local basada en tu instalación de MySQL 8.0.46
def obtener_conexion():
    try:
        conexion = mysql.connector.connect(
            host='localhost',
            port=3306,
            user='root',
            password='Joaquin1',  # Contraseña de tu Workbench
            database='fit_tracker_db'
        )
        return conexion
    except Error as e:
        print(f"[ERROR CRÍTICO] No se pudo conectar a MySQL: {e}")
        return None

def registrar_nuevo_usuario(nombre, password, peso, entrenamientos, objetivo, deficit):
    conn = obtener_conexion()
    if not conn:
        return {"success": False, "message": "Error de conexión a la base de datos."}
    
    cursor = conn.cursor()
    password_encriptada = generate_password_hash(password)
    token_interno = f"fit_live_{secrets.token_hex(16)}"
    
    try:
        cursor.execute("""
            INSERT INTO usuarios (nombre, password_hash, peso, entrenamientos, objetivo, deficit, gemini_api_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (nombre, password_encriptada, peso, entrenamientos, objetivo, deficit, token_interno))
        conn.commit()
        return {"success": True, "message": "Usuario registrado con éxito"}
    except Error as e:
        conn.rollback()
        return {"success": False, "message": f"El nombre de usuario ya existe o hubo un error: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

def verificar_credenciales(nombre, password):
    """Verifica el login y extrae el ID, nombre y la clave de Gemini."""
    conn = obtener_conexion()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, nombre, password_hash, gemini_api_key FROM usuarios WHERE nombre = %s", (nombre,))
        usuario = cursor.fetchone()
        if usuario and check_password_hash(usuario['password_hash'], password):
            return usuario  
        return None
    except Error as e:
        print(f"[ERROR LOGIN] {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def actualizar_gemini_key(usuario_id, api_key_real):
    """Almacena la clave real provista por el usuario en su fila correspondiente."""
    conn = obtener_conexion()
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE usuarios 
            SET gemini_api_key = %s 
            WHERE id = %s
        """, (api_key_real, usuario_id))
        conn.commit()
        return True
    except Error as e:
        print(f"[MySQL ERROR ACTUALIZAR KEY] {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def insertar_alimento(alimento, calorias, proteinas, carbohidratos, grasas, es_milanesa, usuario_id):
    """Inserta un registro de alimento asociándolo obligatoriamente al ID del usuario logueado."""
    conn = obtener_conexion()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO registro_comidas 
            (descripcion_alimento, peso_g, calorias, proteinas_g, carbohidratos_g, grasas_g, es_milanesa, fecha_hora, usuario_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """, (alimento, 100.0, calorias, proteinas, carbohidratos, grasas, es_milanesa, usuario_id))
        conn.commit()
    except Error as e:
        print(f"[ERROR DB] No se pudo insertar alimento para usuario {usuario_id}: {e}")
    finally:
        cursor.close()
        conn.close()

def insertar_entrenamiento(grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg, usuario_id):
    """Inserta una serie de entrenamiento asociándolo obligatoriamente al ID del usuario logueado."""
    conn = obtener_conexion()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        detalles = f"Ejercicio: {ejercicio_clave}. Series: {series}, Reps: {repeticiones}, Peso: {carga_kg}kg."
        cursor.execute("""
            INSERT INTO registro_entrenamientos 
            (tipo_entrenamiento, duracion_minutos, calorias_quemadas_estimadas, detalles_sesion, fecha_hora, usuario_id)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        """, (grupo_muscular, 60, int(carga_kg * 4), detalles, usuario_id))
        conn.commit()
    except Error as e:
        print(f"[ERROR DB] No se pudo insertar entrenamiento para usuario {usuario_id}: {e}")
    finally:
        cursor.close()
        conn.close()

def vaciar_registro_del_dia(usuario_id):
    """Elimina por completo todos los registros de comida del día de hoy del usuario especificado."""
    conn = obtener_conexion()
    if not conn:
        return "Error de conexión."
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM registro_comidas 
            WHERE usuario_id = %s AND DATE(fecha_hora) = CURDATE()
        """, (usuario_id,))
        conn.commit()
        return "Éxito: Todo el historial de alimentación de hoy fue eliminado correctamente."
    except Error as e:
        return f"Fallo operativo al borrar: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def obtener_metricas_globales(usuario_id):
    """Consulta los totales consolidados filtrando estrictamente por el ID de usuario."""
    conn = obtener_conexion()
    if not conn:
        return {
            "calorias_hoy": 0.0, "proteinas_hoy": 0.0, "carbohidratos_hoy": 0.0, "grasas_hoy": 0.0,
            "ultimos_alimentos": [], "ultimos_entrenamientos": []
        }
    cursor = conn.cursor(dictionary=True)
    
    cal_hoy, prot_hoy, carb_hoy, gras_hoy = 0.0, 0.0, 0.0, 0.0
    ultimos_alimentos = []
    ultimos_entrenamientos = []
    
    try:
        cursor.execute("""
            SELECT 
                SUM(calorias) as calorias_totales, 
                SUM(proteinas_g) as proteinas_totales, 
                SUM(carbohidratos_g) as carbohidratos_totales, 
                SUM(grasas_g) as grasas_totales 
            FROM registro_comidas 
            WHERE usuario_id = %s AND DATE(fecha_hora) = CURDATE()
        """, (usuario_id,))
        fila = cursor.fetchone()
        if fila:
            cal_hoy = fila['calorias_totales'] if fila['calorias_totales'] is not None else 0.0
            prot_hoy = fila['proteinas_totales'] if fila['proteinas_totales'] is not None else 0.0
            carb_hoy = fila['carbohidratos_totales'] if fila['carbohidratos_totales'] is not None else 0.0
            gras_hoy = fila['grasas_totales'] if fila['grasas_totales'] is not None else 0.0
            
        cursor.execute("""
            SELECT descripcion_alimento as alimento, proteinas_g as prot, carbohidratos_g as carb, grasas_g as grasa, calorias 
            FROM registro_comidas 
            WHERE usuario_id = %s
            ORDER BY id DESC LIMIT 5
        """, (usuario_id,))
        ultimos_alimentos = cursor.fetchall()

        cursor.execute("""
            SELECT tipo_entrenamiento as grupo, detalles_sesion as ejercicio 
            FROM registro_entrenamientos 
            WHERE usuario_id = %s
            ORDER BY id DESC LIMIT 5
        """, (usuario_id,))
        ultimos_entrenamientos = cursor.fetchall()

    except Error as e:
        print(f"[ERROR CRÍTICO EN QUERY MYSQL] {e}")
    finally:
        cursor.close()
        conn.close()
    
    return {
        "calorias_hoy": round(float(cal_hoy), 1),
        "proteinas_hoy": round(float(prot_hoy), 1),
        "carbohidratos_hoy": round(float(carb_hoy), 1),
        "grasas_hoy": round(float(gras_hoy), 1),
        "ultimos_alimentos": ultimos_alimentos,
        "ultimos_entrenamientos": ultimos_entrenamientos
    }

def obtener_datos_atleta(usuario_id):
    """Recupera el perfil calórico y de entrenamiento de un usuario."""
    conn = obtener_conexion()
    if not conn: 
        return {'peso': 70.0, 'entrenamientos': 5, 'objetivo': 'definicion', 'deficit': -500}
        
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT peso, entrenamientos, objetivo, deficit FROM usuarios WHERE id = %s", (usuario_id,))
        resultado = cursor.fetchone()
        if not resultado:
            return {'peso': 70.0, 'entrenamientos': 5, 'objetivo': 'definicion', 'deficit': -500}
        return resultado
    except Exception as e:
        print(f"[MySQL ERROR OBTENER ATLETA]: {e}")
        return {'peso': 70.0, 'entrenamientos': 5, 'objetivo': 'definicion', 'deficit': -500}
    finally:
        cursor.close()
        conn.close()
        
def init_db():
    # MySQL no requiere inicialización manual de tablas por código si ya están creadas en Workbench,
    # pero se deja esta función vacía para evitar el error de importación desde app.py.
    pass