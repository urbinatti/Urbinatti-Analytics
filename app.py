# =============================================================================
# SERVIDOR BACKEND (FLASK) Y MOTOR MATEMÁTICO DE CONTROL
# PROYECTO: ANALYTICS DASHBOARD - JOAQUÍN URBINATTI
# =============================================================================
from flask import Flask, jsonify, render_template, request, redirect, url_for
import sqlite3
import database
import os
from datetime import datetime  
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Cargar variables de entorno forzando la ruta del directorio actual
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
# RUTA INTELIGENTE: Si está en la nube usa el volumen persistente de Render/Railway, si no, local.
IF_RENDER_DATA = '/data/analytics_urbinati.db'
if os.path.exists('/data') or os.environ.get('RENDER') or os.environ.get('RAILWAY_STATIC_URL'):
    DB_PATH = IF_RENDER_DATA
else:
    DB_PATH = os.path.join(BASE_DIR, 'analytics_urbinati.db')
# CONSTANTES METABÓLICAS ESTABLECIDAS DE FORMA CRUDA PARA JOAQUÍN URBINATTI
PESO_KG = 70
FRECUENCIA_GYM = 5
GASTO_ENERGETICO_BASE = 2400  # Estimación basada en tu tasa metabólica y nivel de actividad alta
DEFICIT_OBJETIVO = 600        # Foco estricto en definición (Rango 500-1000 kcal)
CALORIAS_LIMITE_DIARIO = GASTO_ENERGETICO_BASE - DEFICIT_OBJETIVO # 1800 kcal objetivo

# ---------------------------------------------------------------------
# DEFINICIÓN DE HERRAMIENTAS EXPLICATIVAS PARA LA IA (FUNCTION CALLING)
# ---------------------------------------------------------------------
def registrar_comida_desde_ia(alimento: str, calorias: float, proteinas: float, carbohidratos: float, grasas: float) -> str:
    """Registra un alimento con sus macros calculados directamente en la base de datos SQL."""
    print(f"\n[AUDITORÍA IA] Intentando registrar: {alimento} | Ruta DB: {DB_PATH}")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Guardamos forzando la fecha en texto para ver si hay choque de formatos
        fecha_actual = datetime.now().strftime('%Y-%m-%d') if 'datetime' in globals() else "2026-07-08"
        
        cursor.execute("""
            INSERT INTO nutricion (alimento, calorias, proteinas, carbohidratos, grasas, es_milanesa, fecha)
            VALUES (?, ?, ?, ?, ?, 0, DATE('now', 'localtime'))
        """, (alimento, calorias, proteinas, carbohidratos, grasas))
        
        conn.commit()
        
        # Verificación inmediata si impactó en la tabla
        cursor.execute("SELECT * FROM nutricion ORDER BY id DESC LIMIT 1")
        ultimo_registro = cursor.fetchone()
        print(f"[AUDITORÍA IA] ÉXITO REAL EN SQL. Último renglón guardado: {ultimo_registro}")
        
        conn.close()
        return f"Éxito: Se ha registrado '{alimento}' ({calorias} kcal) en la base de datos."
    except Exception as e:
        print(f"[AUDITORÍA IA] CRASH AL ESCRIBIR EN SQL: {str(e)}")
        return f"Error físico en SQL: {str(e)}"

def resetear_calorias_del_dia() -> str:
    """Elimina por completo todos los registros de comida del día de hoy en la base de datos SQL."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM nutricion WHERE DATE(fecha) = DATE('now', 'localtime')")
    conn.commit()
    conn.close()
    return "Éxito: Todo el historial de alimentación de hoy fue eliminado correctamente de la base de datos SQL."

def registrar_entrenamiento_desde_ia(grupo_muscular: str, ejercicio_clave: str, series: int, repeticiones: int, carga_kg: float) -> str:
    """Registra una serie o ejercicio realizado en el gimnasio usando las columnas reales de SQL."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO entrenamientos (grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg, fecha)
        VALUES (?, ?, ?, ?, ?, DATE('now', 'localtime'))
    """, (grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg))
    conn.commit()
    conn.close()
    return f"Éxito: Se registró en SQL: {grupo_muscular} - {ejercicio_clave}: {series}x{repeticiones} con {carga_kg} kg."

@app.route("/static/sw.js")
def serve_sw():
    return app.send_static_file("sw.js")

@app.route("/")
def index():
    metricas = database.obtener_metricas_globales()
    balance = CALORIAS_LIMITE_DIARIO - metricas["calorias_hoy"]
    estado_deficit = "DENTRO DEL RANGO" if balance >= 0 else "EXCEDIDO DEL LÍMITE"
    
    return render_template(
        "index.html",
        metricas=metricas,
        limite_calorias=CALORIAS_LIMITE_DIARIO,
        balance=balance,
        estado_deficit=estado_deficit,
        peso=PESO_KG,
        frecuencia=FRECUENCIA_GYM
    )

@app.route("/registrar_entrenamiento", methods=["POST"])
def registrar_entrenamiento():
    grupo = request.form.get("grupo")
    ejercicio = request.form.get("ejercicio")
    series = int(request.form.get("series"))
    reps = int(request.form.get("reps"))
    carga = float(request.form.get("carga"))
    
    database.insertar_entrenamiento(grupo, ejercicio, series, reps, carga)
    return redirect(url_for("index"))

@app.route("/registrar_nutricion", methods=["POST"])
def registrar_nutricion():
    alimento = request.form.get("alimento").strip()
    es_mili = 1 if "milanesa" in alimento.lower() else 0
    grams_raw = request.form.get("gramos")
    gramos = float(grams_raw) if grams_raw else 0.0
    
    if es_mili:
        carne_g = gramos * 0.485
        pan_g = gramos * 0.515
        prot_totales = (carne_g * 0.22) + (pan_g * 0.08)
        carb_totales = (pan_g * 0.65)
        grasa_totales = (carne_g * 0.03) + (pan_g * 0.12) 
        calorias_totales = (prot_totales * 4) + (carb_totales * 4) + (grasa_totales * 9)
        alimento += " (Ratio Auditado 48.5/51.5%)"
    else:
        prot_raw = request.form.get("prot")
        carb_raw = request.form.get("carb")
        grasa_raw = request.form.get("grasa")
        
        prot_totales = float(prot_raw) * (gramos / 100) if prot_raw else 0.0
        carb_totales = float(carb_raw) * (gramos / 100) if carb_raw else 0.0
        grasa_totales = float(grasa_raw) * (gramos / 100) if grasa_raw else 0.0
        calorias_totales = (prot_totales * 4) + (carb_totales * 4) + (grasa_totales * 9)

    database.insertar_alimento(alimento, calorias_totales, prot_totales, carb_totales, grasa_totales, es_mili)
    return redirect(url_for("index"))

@app.route('/chat', methods=['POST'])
def chat_api():
    data = request.get_json()
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'response': 'No se recibió ningún mensaje.'})
    
    try:
        metrics = database.obtener_metricas_globales()
        calorias_hoy = metrics.get("calorias_hoy", 0)
        
        # Traemos el historial apuntando obligatoriamente a la ruta unificada absoluta
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT grupo_muscular, ejercicio_clave, series, repeticiones, carga_kg, fecha FROM entrenamientos ORDER BY id DESC")
        historial_gimnasio = cursor.fetchall()
        conn.close()
        
        instrucciones_sistema = (
            "Sos el motor de Inteligencia Artificial integrado en el URBINATTI PERFORMANCE ANALYTICS. "
            "Tu usuario es Joaquín Urbinatti, pesa 70 kg y entrena 5 veces por semana en el gimnasio. "
            "Su objetivo físico es estricto: mantener un déficit calórico diario enfocado en definición de entre 500 y 1000 calorías. "
            "Regla obligatoria para Milanesas: Si te menciona o pide guardar milanesas, calculás los macros usando "
            "el ratio exacto: 48.5% carne real y 51.5% rebozado. Considerá que absorbe aceite y la densidad calórica es alta. "
            "Sé siempre totalmente crudo, realista, objetivo y sincero con tus respuestas, sin proteger sus sentimientos. "
            f"Contexto nutricional de hoy: Joaquín consumió hoy {calorias_hoy} kcal. "
            f"Historial COMPLETO de entrenamientos inyectados en SQL: {historial_gimnasio}. "
            "Usa este historial para calcular porcentajes exactos de sobrecarga progresiva cuando Joaquín te pregunte cómo viene progresando en un ejercicio. "
            "Tenés herramientas disponibles para modificar la base de datos de forma obligatoria: "
            "1. Si te pide registrar una comida: invocas 'registrar_comida_desde_ia'. "
            "2. Si te pide borrar o reiniciar el día: invocas 'resetear_calorias_del_dia'. "
            "3. Si te pide registrar un ejercicio/entrenamiento: deducís el grupo muscular, series, repeticiones y carga_kg, e invocas 'registrar_entrenamiento_desde_ia'."
        )
        
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        herramientas_disponibles = [registrar_comida_desde_ia, resetear_calorias_del_dia, registrar_entrenamiento_desde_ia]
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=instrucciones_sistema,
                temperature=0.2,
                tools=herramientas_disponibles
            )
        )
        
        if response.function_calls:
            for call in response.function_calls:
                nombre_funcion = call.name
                argumentos = call.args
                
                if nombre_funcion == "registrar_comida_desde_ia":
                    resultado_db = registrar_comida_desde_ia(
                        alimento=argumentos.get("alimento"),
                        calorias=float(argumentos.get("calorias")),
                        proteinas=float(argumentos.get("proteinas")),
                        carbohidratos=float(argumentos.get("carbohidratos")),
                        grasas=float(argumentos.get("grasas"))
                    )
                elif nombre_funcion == "resetear_calorias_del_dia":
                    resultado_db = resetear_calorias_del_dia()
                elif nombre_funcion == "registrar_entrenamiento_desde_ia":
                    resultado_db = registrar_entrenamiento_desde_ia(
                        grupo_muscular=argumentos.get("grupo_muscular"),
                        ejercicio_clave=argumentos.get("ejercicio_clave"),
                        series=int(argumentos.get("series")),
                        repeticiones=int(argumentos.get("repeticiones")),
                        carga_kg=float(argumentos.get("carga_kg"))
                    )
                else:
                    resultado_db = "Función no reconocida."
                
                response_final = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        user_message,
                        response.candidates[0].content,
                        types.Content(
                            role="tool",
                            parts=[types.Part.from_function_response(
                                name=nombre_funcion,
                                response={"result": resultado_db}
                            )]
                        )
                    ],
                    config=types.GenerateContentConfig(system_instruction=instrucciones_sistema)
                )
                return jsonify({'response': response_final.text})

        return jsonify({'response': response.text})
        
    except Exception as e:
        print(f"Error crítico en la API de Gemini: {e}")
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            import re
            from datetime import datetime, timezone, timedelta
            if "RequestsPerDay" in error_str or "FreeTier" in error_str:
                ahora_utc = datetime.now(timezone.utc)
                mañana_utc = datetime.combine(ahora_utc.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
                tiempo_restante = mañana_utc - ahora_utc
                horas = int(tiempo_restante.total_seconds() // 3600)
                minutos = int((tiempo_restante.total_seconds() % 3600) // 60)
                tiempo_espera_real = f"{horas} horas y {minutos} minutos" if horas > 0 else f"{minutos} minutos"
                return jsonify({'response': f"⚠️ Cuota diaria agotada: Has consumido tus 20 consultas permitidas. Acceso restaurado en {tiempo_espera_real}."})
            
            tiempo_espera = "unos segundos"
            try:
                match = re.search(r'retry in ([\d\.]+)\s*s', error_str)
                if match:
                    segundos = float(match.group(1))
                    tiempo_espera = f"{int(segundos // 60)} minutos y {int(segundos % 60)} segundos" if segundos > 60 else f"{int(segundos)} segundos"
            except Exception: pass
            return jsonify({'response': f"⚠️ Saturación temporal: Vas muy rápido. Esperá exactamente {tiempo_espera}."})
        return jsonify({'response': f"Error operativo en el backend: {str(e)}"})

# =============================================================================
# ARRANQUE DE LA APLICACIÓN (ESCUCHANDO EN TODA LA RED PARA MI IPHONE)
# =============================================================================
if __name__ == "__main__":
    # Lee el puerto asignado por la nube, si no encuentra ninguno (local), usa el 5000
    puerto = int(os.environ.get("PORT", 5000))
    # En producción debug debe ser False para evitar fallas de seguridad
    es_produccion = os.environ.get('RENDER') is not None or os.environ.get('RAILWAY_STATIC_URL') is not None
    app.run(debug=not es_produccion, host='0.0.0.0', port=puerto)