import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from google import genai
import database

app = Flask(__name__)
app.secret_key = os.urandom(24)

database.init_db()

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
    conn.close()
    
    consumos_dict = {
        "calorias_cons": consumo["calorias_cons"],
        "proteinas_cons": consumo["proteinas_cons"],
        "grasas_cons": consumo["grasas_cons"],
        "carbs_cons": consumo["carbs_cons"]
    }
    
    return render_template('index.html', user_data=user_data, consumos=consumos_dict)

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    email_demo = 'matias@urbinatti.com'
    session['user_email'] = email_demo
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM usuarios WHERE email = ?", (email_demo,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (email, nombre, onboarding_completado) VALUES (?, ?, ?)",
                       (email_demo, 'Joaquín Urbinatti', 0))
        conn.commit()
        
    cursor.execute("SELECT onboarding_completado FROM usuarios WHERE email = ?", (email_demo,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] == 1:
        return redirect(url_for('index'))
    return redirect(url_for('onboarding'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/onboarding', methods=['GET', 'POST'])
def onboarding():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
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
        
        cursor.execute("SELECT sexo FROM usuarios WHERE email = ?", (session['user_email'],))
        row = cursor.fetchone()
        sexo = row['sexo'] if row else 'M'
        
        nutri = calcular_nutricion(peso, altura, edad, sexo, dias, objetivo)
        
        cursor.execute('''
            UPDATE usuarios SET peso_kg=?, altura_cm=?, edad=?, dias_entreno=?, objetivo=?,
            calorias_objetivo=?, proteinas_objetivo=?, grasas_objetivo=?, carbs_objetivo=?
            WHERE email=?
        ''', (peso, altura, edad, dias, objetivo, nutri['calorias'], nutri['proteinas'], nutri['grasas'], nutri['carbs'], session['user_email']))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
        
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (session['user_email'],))
    user_data = cursor.fetchone()
    conn.close()
    return render_template('configuracion.html', user_data=user_data)

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_email' not in session:
        return jsonify({'respuesta': 'No autorizado'}), 401
        
    data = request.get_json()
    mensaje = data.get('mensaje', '')
    email = session['user_email']
    start_time, end_time = get_effective_date_window()
    
    import sqlite3
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    
    api_key = user['gemini_api_key'] or os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Eres un asistente nutricional crudo, objetivo y sin rodeos. Analiza la siguiente comida del usuario: "{mensaje}".
    Devuelve estrictamente un JSON válido con este formato exacto (sin texto adicional fuera del JSON):
    {{
      "respuesta_ia": "Breve comentario objetivo sobre el plato con su desglose",
      "calorias": 0.0,
      "proteinas": 0.0,
      "grasas": 0.0,
      "carbohidratos": 0.0
    }}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        import json
        texto_limpio = response.text.strip().replace('```json', '').replace('```', '')
        parsed = json.loads(texto_limpio)
        
        timestamp_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO registros_comidas (descripcion, peso, calorias, proteinas, carbohidratos, grasas, timestamp, usuario_email) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (mensaje, 0.0, parsed['calorias'], parsed['proteinas'], parsed['carbohidratos'], parsed['grasas'], timestamp_actual, email))
        conn.commit()
        
        cursor.execute('''
            SELECT 
                COALESCE(SUM(calorias), 0) as calorias_cons,
                COALESCE(SUM(proteinas), 0) as proteinas_cons,
                COALESCE(SUM(grasas), 0) as grasas_cons,
                COALESCE(SUM(carbohidratos), 0) as carbs_cons
            FROM registros_comidas 
            WHERE usuario_email = ? AND timestamp >= ? AND timestamp < ?
        ''', (email, start_time, end_time))
        updated_consumo = cursor.fetchone()
        conn.close()
        
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
        return jsonify({'respuesta': f'Error procesando la ingesta: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)