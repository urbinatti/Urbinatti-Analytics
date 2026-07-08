# =============================================================================
# MOTOR DE BASE DE DATOS RELACIONAL (SQLITE3) - REPARADO CON COLUMNAS REALES
# PROYECTO: ANALYTICS DASHBOARD - JOAQUÍN URBINATTI
# =============================================================================
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists('/data') or os.environ.get('RENDER') or os.environ.get('RAILWAY_STATIC_URL'):
    DB_PATH = '/data/analytics_urbinati.db'
else:
    DB_PATH = os.path.join(BASE_DIR, 'analytics_urbinati.db')

def insertar_alimento_directo(alimento, proteinas, carbohidratos, grasas, calorias):
    """Inserta un registro de alimento procesado desde el formulario manual."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO nutricion (alimento, proteinas_g, carbohidratos_g, grasas_g, calorias_totales, es_milanesa, fecha)
            VALUES (?, ?, ?, ?, ?, 0, DATE('now', 'localtime'))
        """, (alimento, proteinas, carbohidratos, grasas, calorias))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] No se pudo insertar en insertar_alimento_directo: {e}")
    finally:
        conn.close()
    return {"status": "success", "message": f"Alimento '{alimento}' registrado con éxito."}

def vaciar_registro_del_dia():
    """Elimina por completo todos los registros de comida del día de hoy."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM nutricion WHERE DATE(fecha) = DATE('now', 'localtime')")
        conn.commit()
        conn.close()
        return "Éxito: Todo el historial de alimentación de hoy fue eliminado correctamente de la base de datos SQL."
    except Exception as e:
        conn.close()
        return f"Fallo operativo al borrar en SQL: {str(e)}"

def insertar_alimento(alimento, calorias, proteinas, carbohidratos, grasas, es_milanesa):
    """Inserta un registro completo de alimento calculando la fecha de forma nativa en SQL."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO nutricion (alimento, calorias_totales, proteinas_g, carbohidratos_g, grasas_g, es_milanesa, fecha)
            VALUES (?, ?, ?, ?, ?, ?, DATE('now', 'localtime'))
        """, (alimento, calorias, proteinas, carbohidratos, grasas, es_milanesa))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] No se pudo insertar en insertar_alimento: {e}")
    finally:
        conn.close()

def insertar_entrenamiento(grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg):
    """Inserta una serie de entrenamiento usando las columnas reales validadas por consola."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO entrenamientos (grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg, fecha)
            VALUES (?, ?, ?, ?, ?, DATE('now', 'localtime'))
        """, (grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] No se pudo insertar en insertar_entrenamiento: {e}")
    finally:
        conn.close()

def obtener_metricas_globales():
    """Consulta los totales consolidados mapeando las columnas auditadas."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cal_hoy, prot_hoy, carb_hoy, gras_hoy = 0.0, 0.0, 0.0, 0.0
    ultimos_alimentos = []
    ultimos_entrenamientos = []
    
    try:
        # 1. Sumatoria usando los nombres exactos de tus campos reales
        cursor.execute("""
            SELECT 
                SUM(calorias_totales), 
                SUM(proteinas_g), 
                SUM(carbohidratos_g), 
                SUM(grasas_g) 
            FROM nutricion 
            WHERE DATE(fecha) = DATE('now', 'localtime')
        """)
        fila = cursor.fetchone()
        if fila:
            cal_hoy = fila[0] if fila[0] is not None else 0.0
            prot_hoy = fila[1] if fila[1] is not None else 0.0
            carb_hoy = fila[2] if fila[2] is not None else 0.0
            gras_hoy = fila[3] if fila[3] is not None else 0.0
            
        # 2. Últimos 5 de alimentación con la estructura corregida
        cursor.execute("SELECT alimento, proteinas_g, carbohidratos_g, grasas_g, calorias_totales FROM nutricion ORDER BY id DESC LIMIT 5")
        ultimos_alimentos = [
            {"alimento": f[0], "prot": f[1], "carb": f[2], "grasa": f[3], "calorias": f[4]}
            for f in cursor.fetchall()
        ]
    except Exception as e:
        print(f"[ERROR CRÍTICO EN QUERY NUTRICION] {e}")
    
    try:
        # 3. Últimos 5 de entrenamientos
        cursor.execute("SELECT grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg FROM entrenamientos ORDER BY id DESC LIMIT 5")
        ultimos_entrenamientos = [
            {"grupo": f[0], "ejercicio": f[1], "series": f[2], "reps": f[3], "carga": f[4]}
            for f in cursor.fetchall()
        ]
    except Exception as e:
        print(f"[ERROR EN ENTRENAMIENTOS] {e}")

    conn.close()
    
    return {
        "calorias_hoy": round(cal_hoy, 1),
        "proteinas_hoy": round(prot_hoy, 1),
        "carbohidratos_hoy": round(carb_hoy, 1),
        "grasas_hoy": round(gras_hoy, 1),
        "ultimos_alimentos": ultimos_alimentos,
        "ultimos_entrenamientos": ultimos_entrenamientos
    }