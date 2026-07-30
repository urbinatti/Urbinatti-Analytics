os = __import__('os')
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
from google import genai
import database
from authlib.integrations.flask_client import OAuth
import json
import sqlite3

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave_fija_super_segura_urbinati_2026")
app.permanent_session_lifetime = timedelta(days=30)
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

database.init_db()

oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

def get_effective_date_window():
    now = datetime.now()
    if now.hour < 4:
        effective_date = now - timedelta(days=1)
    else:
        effective_date = now
    
    date_str = effective_date.strftime('%Y-%m-%d')
    start_time = f"{date_str} 04:00:00"
    next_day = (effective_date + timedelta(days=1)).strftime('%Y-%m-%d')
    end_time = f"{next_day} 04:00:00"
    
    return start_time, end_time

def calcular_nutricion(peso, altura, edad, sexo, dias_entreno, objetivo):
    if sexo == 'M':
        bmr = (10 * peso) + (6.25 * altura) - (5 * edad) + 5
    else:
        bmr = (10 * peso) + (6.25 * altura) - (5 * edad) - 161

    if dias_entreno <= 1:
        tdee = bmr * 1.2
    elif dias_entreno <= 3:
        tdee = bmr * 1.375
    elif dias_entreno <= 5:
        tdee = bmr * 1.55
    else:
        tdee = bmr * 1.725

    es_volumen = False
    if objetivo == 'perdida_agresiva':
        calorias = tdee * 0.75
    elif objetivo == 'perdida_controlada':
        calorias = tdee * 0.85
    elif objetivo == 'mantenimiento':
        calorias = tdee
    elif objetivo == 'volumen_limpio':
        calorias = tdee * 1.10
        es_volumen = True
    elif objetivo == 'volumen_fuerte':
        calorias = tdee * 1.20
        es_volumen = True
    else:
        calorias = tdee

    proteinas_g = peso * 2.0 if es_volumen else peso * 1.5
    grasas_g = peso * 0.8
    calorias_restantes = calorias - ((proteinas_g * 4) + (grasas_g * 9))
    carbs_g = max(0, calorias_restantes / 4)

    return {
        "calorias": round(calorias),
        "proteinas": round(proteinas_g, 1),
        "grasas": round(grasas_g, 1),
        "carbs": round(carbs_g, 1)
    }

@app.route('/')
def index():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    email = session['user_email']
    start_time, end_time = get_effective_date_window()
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    user_data = cursor.fetchone()
    
    if not user_data or not user_data['onboarding_completado']:
        conn.close()
        return redirect(url_for('onboarding'))
    
    cursor.execute('''
        SELECT 
            COALESCE(SUM(calorias), 0) as calorias_cons,
            COALESCE(SUM(proteinas), 0) as proteinas_cons,
            COALESCE(SUM(grasas), 0) as grasas_cons,
            COALESCE(SUM(carbohidratos), 0) as carbs_cons
        FROM registros_comidas 
        WHERE usuario_email = ? AND timestamp >= ? AND timestamp < ?
    ''', (email, start_time, end_time))
    consumo = cursor.fetchone()
    
    cursor.execute('''
        SELECT rol, mensaje FROM historial_chat 
        WHERE usuario_email = ? AND timestamp >= ? AND timestamp < ?
        ORDER BY timestamp ASC
    ''', (email, start_time, end_time))
    chat_history = cursor.fetchall()
    
    conn.close()
    
    consumos_dict = {
        "calorias_cons": consumo["calorias_cons"],
        "proteinas_cons": consumo["proteinas_cons"],
        "grasas_cons": consumo["grasas_cons"],
        "carbs_cons": consumo["carbs_cons"]
    }
    
    has_key = False
    if user_data and 'gemini_api_key' in user_data.keys() and user_data['gemini_api_key']:
        db_k = str(user_data['gemini_api_key']).strip()
        if db_k not in ["", "None", "null", "undefined"]:
            has_key = True
            
    if not has_key:
        env_k = os.getenv("GEMINI_API_KEY")
        if env_k and str(env_k).strip() not in ["", "None", "null", "undefined"]:
            has_key = True
    
    return render_template('index.html', user_data=user_data, consumos=consumos_dict, has_key=has_key, chat_history=chat_history)

@app.route('/login')
def login():
    if 'user_email' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    redirect_uri = url_for('auth', _external=True)
    # Le mandamos "select_account" y le sumamos "consent" para que Google no tenga margen de evadir la pantalla
    return google.authorize_redirect(redirect_uri, prompt='select_account consent')

@app.route('/auth')
def auth():
    # Google nos devuelve acá con el token real
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    
    email_real = user_info['email']
    nombre_real = user_info.get('name', 'Usuario')
    
    session.permanent = True
    session['user_email'] = email_real
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Verificamos si el usuario real existe en nuestra base
    cursor.execute("SELECT email, onboarding_completado FROM usuarios WHERE email = ?", (email_real,))
    row = cursor.fetchone()
    
    if not row:
        # Es un usuario nuevo, lo registramos
        cursor.execute("INSERT INTO usuarios (email, nombre, onboarding_completado) VALUES (?, ?, 0)",
                       (email_real, nombre_real))
        conn.commit()
        conn.close()
        return redirect(url_for('onboarding'))
    
    conn.close()
    
    if row[1] == 1:
        return redirect(url_for('index'))
    return redirect(url_for('onboarding'))

@app.route('/logout')
def logout():
    session.clear() # Vacía el diccionario en el servidor
    respuesta = redirect(url_for('login'))
    # Literalmente le ordenamos al navegador que ponga la fecha de expiración de la cookie en 0 (la destruye)
    respuesta.set_cookie('session', '', expires=0) 
    return respuesta

@app.route('/onboarding', methods=['GET', 'POST'])
def onboarding():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    session.permanent = True
    if request.method == 'POST':
        peso = float(request.form['peso_kg'])
        altura = int(request.form['altura_cm'])
        edad = int(request.form['edad'])
        sexo = request.form['sexo']
        dias = int(request.form['dias_entreno'])
        objetivo = request.form['objetivo']
        
        nutri = calcular_nutricion(peso, altura, edad, sexo, dias, objetivo)
        
        import sqlite3
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE usuarios SET peso_kg=?, altura_cm=?, edad=?, sexo=?, dias_entreno=?, objetivo=?,
            calorias_objetivo=?, proteinas_objetivo=?, grasas_objetivo=?, carbs_objetivo=?, onboarding_completado=1
            WHERE email=?
        ''', (peso, altura, edad, sexo, dias, objetivo, nutri['calorias'], nutri['proteinas'], nutri['grasas'], nutri['carbs'], session['user_email']))
        conn.commit()
        conn.close()
        
        return redirect(url_for('index'))
        
    return render_template('onboarding.html')

@app.route('/configuracion', methods=['GET', 'POST'])
def configuracion():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        peso = float(request.form['peso_kg'])
        altura = int(request.form['altura_cm'])
        edad = int(request.form['edad'])
        dias = int(request.form['dias_entreno'])
        objetivo = request.form['objetivo']
        gemini_key = request.form.get('gemini_api_key', '').strip()
        
        cursor.execute("SELECT sexo FROM usuarios WHERE email = ?", (session['user_email'],))
        row = cursor.fetchone()
        sexo = row['sexo'] if row else 'M'
        
        nutri = calcular_nutricion(peso, altura, edad, sexo, dias, objetivo)
        
        cursor.execute('''
            UPDATE usuarios SET peso_kg=?, altura_cm=?, edad=?, dias_entreno=?, objetivo=?,
            calorias_objetivo=?, proteinas_objetivo=?, grasas_objetivo=?, carbs_objetivo=?, gemini_api_key=?
            WHERE email=?
        ''', (peso, altura, edad, dias, objetivo, nutri['calorias'], nutri['proteinas'], nutri['grasas'], nutri['carbs'], gemini_key, session['user_email']))
            
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
        
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (session['user_email'],))
    user_data = cursor.fetchone()
    conn.close()
    return render_template('configuracion.html', user_data=user_data)

@app.route('/guardar-key', methods=['POST'])
def guardar_key():
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'No autorizado'}), 401
    data = request.get_json()
    key = data.get('api_key', '').strip()
    if not key:
        return jsonify({'success': False, 'error': 'Key vacía'})
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET gemini_api_key = ? WHERE email = ?", (key, session['user_email']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# --- RUTA PARA GUARDAR SUSCRIPCIÓN PUSH ---
@app.route('/api/guardar_suscripcion', methods=['POST'])
def guardar_suscripcion():
    # Verificamos que el usuario esté logueado
    if 'user' not in session:
        return jsonify({"error": "Usuario no autorizado"}), 401
    
    # Obtenemos el email de la sesión actual de Google
    email_usuario = session['user'].get('email')
    
    # Agarramos los datos del permiso que manda el celular
    datos_suscripcion = request.get_json()
    suscripcion_str = json.dumps(datos_suscripcion)

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # Guardamos el permiso en la base de datos
        cursor.execute('''
            INSERT INTO suscripciones_push (email, suscripcion_json) 
            VALUES (?, ?)
        ''', (email_usuario, suscripcion_str))
        
        conn.commit()
        conn.close()
        return jsonify({"status": "Suscripción guardada con éxito"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_email' not in session:
        return jsonify({'respuesta': 'No autorizado'}), 401
        
    data = request.get_json()
    mensaje = data.get('mensaje', '')
    email = session['user_email']
    start_time, end_time = get_effective_date_window()
    timestamp_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    cursor.execute('''
        SELECT 
            COALESCE(SUM(calorias), 0) as calorias_cons,
            COALESCE(SUM(proteinas), 0) as proteinas_cons,
            COALESCE(SUM(grasas), 0) as grasas_cons,
            COALESCE(SUM(carbohidratos), 0) as carbs_cons
        FROM registros_comidas 
        WHERE usuario_email = ? AND timestamp >= ? AND timestamp < ?
    ''', (email, start_time, end_time))
    consumo_actual = cursor.fetchone()
    conn.close()
    
    api_key = None
    if user and 'gemini_api_key' in user.keys() and user['gemini_api_key']:
        db_key = str(user['gemini_api_key']).strip()
        if db_key not in ["", "None", "null", "undefined"]:
            api_key = db_key
            
    if not api_key:
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key and str(env_key).strip() not in ["", "None", "null", "undefined"]:
            api_key = str(env_key).strip()
    
    if not api_key:
        return jsonify({'respuesta': '🔒 Falta configurar tu API Key. Generala en el botón de arriba y pegala en el campo correspondiente para chatear.'})
    
    try:
        conn2 = sqlite3.connect('database.db')
        conn2.row_factory = sqlite3.Row
        cursor2 = conn2.cursor()
        
        # 1. Guardar mensaje del usuario
        cursor2.execute('''
            INSERT INTO historial_chat (usuario_email, rol, mensaje, timestamp) 
            VALUES (?, ?, ?, ?)
        ''', (email, 'user', mensaje, timestamp_actual))
        conn2.commit()

        client = genai.Client(api_key=api_key)
        
        # Prompt mejorado con la instrucción de "deshacer"
        prompt = f"""
        Eres la IA central de "Urbinatti Analytics", un avanzado asistente nutricional.

        CONTEXTO DEL USUARIO:
        - Nombre: {user['nombre']}
        - Peso: {user['peso_kg']} kg
        - Frecuencia de entreno: {user['dias_entreno']} días/sem.
        - Objetivo general: {user['objetivo']}
        - Meta Diaria: {user['calorias_objetivo']} kcal (Prot: {user['proteinas_objetivo']}g, Carbs: {user['carbs_objetivo']}g, Grasas: {user['grasas_objetivo']}g)
        - Consumo HOY (hasta ahora): {consumo_actual['calorias_cons']} kcal (Prot: {consumo_actual['proteinas_cons']}g, Carbs: {consumo_actual['carbs_cons']}g, Grasas: {consumo_actual['grasas_cons']}g)

        REGLAS DE NEGOCIO Y COMPORTAMIENTO:
        1. Acción "charla": Si el usuario solo saluda, pregunta cosas o pide proyecciones, devuelve "accion": "charla" y valores 0.0.
        2. Acción "registrar": Si el usuario ingresa una comida consumida, analiza con desglose fino y devuelve "accion": "registrar".
        3. Acción "deshacer": Si el usuario te indica EXPLÍCITAMENTE que cometió un error y te pide BORRAR, ELIMINAR o DESHACER la última ingesta o registro, devuelve "accion": "deshacer" y valores 0.0. Aclárale en la respuesta que el último registro fue eliminado.
        4. Tono: Directo, crudo, objetivo y realista.
        5. Factor Milanesa: Si menciona "milanesa", aplica EXACTAMENTE 48.5% carne real y 51.5% rebozado/pan.
        6. Cortes con hueso: Deduce peso neto vs peso bruto.
        7. Transparencia: Aclara SIEMPRE si sumaste información externa.
        8. Formato: Usa tablas Markdown.

        MENSAJE DEL USUARIO: "{mensaje}"

        SALIDA ESTRICTAMENTE REQUERIDA (JSON VÁLIDO SIN TEXTO EXTRA):
        {{
          "respuesta_ia": "Tu respuesta conversacional o el análisis nutricional en Markdown.",
          "accion": "registrar" | "charla" | "deshacer",
          "calorias": 0.0,
          "proteinas": 0.0,
          "grasas": 0.0,
          "carbohidratos": 0.0
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt,
        )
        import json
        texto_limpio = response.text.strip().replace('```json', '').replace('```', '')
        parsed = json.loads(texto_limpio)
        
        # 2. Guardar respuesta de la IA
        cursor2.execute('''
            INSERT INTO historial_chat (usuario_email, rol, mensaje, timestamp) 
            VALUES (?, ?, ?, ?)
        ''', (email, 'ia', parsed['respuesta_ia'], timestamp_actual))
        conn2.commit()

        accion_ia = parsed.get('accion', 'charla')

        if accion_ia == 'deshacer':
            # Borrar el ÚLTIMO registro del día actual de este usuario
            cursor2.execute('''
                DELETE FROM registros_comidas 
                WHERE id = (
                    SELECT id FROM registros_comidas 
                    WHERE usuario_email = ? AND timestamp >= ? AND timestamp < ?
                    ORDER BY timestamp DESC LIMIT 1
                )
            ''', (email, start_time, end_time))
            conn2.commit()
            
        elif accion_ia == 'registrar' and (parsed.get('calorias', 0) > 0 or parsed.get('proteinas', 0) > 0 or parsed.get('carbohidratos', 0) > 0 or parsed.get('grasas', 0) > 0):
            # Insertar nueva comida
            cursor2.execute('''
                INSERT INTO registros_comidas (descripcion, peso, calorias, proteinas, carbohidratos, grasas, timestamp, usuario_email) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mensaje, 0.0, parsed['calorias'], parsed['proteinas'], parsed['carbohidratos'], parsed['grasas'], timestamp_actual, email))
            conn2.commit()
            
        # Recalcular consumos SIEMPRE al final (ya sea que borró, agregó o no hizo nada)
        cursor2.execute('''
            SELECT 
                COALESCE(SUM(calorias), 0) as calorias_cons,
                COALESCE(SUM(proteinas), 0) as proteinas_cons,
                COALESCE(SUM(grasas), 0) as grasas_cons,
                COALESCE(SUM(carbohidratos), 0) as carbs_cons
            FROM registros_comidas 
            WHERE usuario_email = ? AND timestamp >= ? AND timestamp < ?
        ''', (email, start_time, end_time))
        updated_consumo = cursor2.fetchone()
            
        conn2.close()
            
        return jsonify({
            'respuesta': parsed['respuesta_ia'],
            'consumos': {
                'calorias_cons': updated_consumo['calorias_cons'],
                'proteinas_cons': updated_consumo['proteinas_cons'],
                'grasas_cons': updated_consumo['grasas_cons'],
                'carbs_cons': updated_consumo['carbs_cons']
            }
        })
    except Exception as e:
        return jsonify({'respuesta': f'Error en el servidor procesando tu solicitud: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)