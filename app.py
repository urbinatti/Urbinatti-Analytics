import os
import requests
from google import genai
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from database import (
    init_db, 
    obtener_usuario_por_email, 
    registrar_o_actualizar_usuario_google, 
    guardar_datos_onboarding
)

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Falta configurar la SECRET_KEY en el archivo .env")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# Inicializar la base de datos al arrancar
init_db()

def calcular_metricas_usuario(peso, altura, edad, sexo, dias_entreno, objetivo):
    if sexo.upper() == 'M':
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
        
    ajustes = {
        'perdida_agresiva': -750,
        'perdida_controlada': -400,
        'mantenimiento': 0,
        'volumen_limpio': 300,
        'volumen_fuerte': 600
    }
    
    calorias_objetivo = tdee + ajustes.get(objetivo, 0)
    
    return int(round(bmr)), int(round(tdee)), int(round(calorias_objetivo))

@app.route('/chat', methods=['POST'])
def chat_ia():
    if 'usuario' not in session:
        return {"error": "No autorizado"}, 401
        
    data = request.get_json()
    mensaje_usuario = data.get('mensaje', '')
    
    if not mensaje_usuario:
        return {"error": "Mensaje vacío"}, 400
        
    email = session['usuario']
    usuario = obtener_usuario_por_email(email)
    
    # Extraer estrictamente la API key propia del usuario desde la base de datos
    api_key = usuario.get('gemini_api_key')
    
    # Validar si el usuario cargó su key real (evitando el token interno por defecto)
    if not api_key or api_key.startswith('fit_live_'):
        return {"respuesta": "No tenés configurada tu API key personal de Gemini. Cargala en tu configuración para poder usar el chat."}
    
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Eres un asistente nutricional estricto, crudo y objetivo. 
        El usuario ha consumido el siguiente alimento o plato: "{mensaje_usuario}".
        Calcula de forma realista las calorías, proteínas, carbohidratos y grasas. 
        Si menciona "milanesa", recuerda usar el ratio de 48.5% carne real y 51.5% rebozado.
        Devuelve la respuesta en formato de texto directo, claro y conciso indicando:
        - Calorías estimadas
        - Proteínas (g)
        - Carbohidratos (g)
        - Grasas (g)
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        return {"respuesta": response.text}
        
    except Exception as e:
        return {"respuesta": f"Error al procesar con la IA: {str(e)}"}

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login_view'))
    
    email = session['usuario']
    usuario = obtener_usuario_por_email(email)
    
    if not usuario or not usuario.get('onboarding_completado'):
        return redirect(url_for('onboarding'))
        
    return render_template('index.html', user_data=usuario)

@app.route('/login')
def login_view():
    if 'usuario' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    if not GOOGLE_CLIENT_ID:
        return "Error: GOOGLE_CLIENT_ID no está configurado en las variables de entorno.", 500
    
    redirect_uri = url_for('authorize_google', _external=True)
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile"
    )
    return redirect(google_auth_url)

@app.route('/login/google/callback')
def authorize_google():
    code = request.args.get('code')
    if not code:
        return "Error: No se recibió el código de autorización de Google.", 400
    
    redirect_uri = url_for('authorize_google', _external=True)
    
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    token_r = requests.post(token_url, data=token_data)
    token_json = token_r.json()
    
    if "access_token" not in token_json:
        return f"Error al obtener el token de Google: {token_json}", 400
        
    user_info_r = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {token_json['access_token']}"}
    )
    user_info = user_info_r.json()
    
    email = user_info.get('email')
    nombre = user_info.get('name')
    
    registrar_o_actualizar_usuario_google(email, nombre)
    
    session['usuario'] = email
    session['nombre'] = nombre
    
    usuario_db = obtener_usuario_por_email(email)
    if not usuario_db or not usuario_db.get('onboarding_completado'):
        return redirect(url_for('onboarding'))
        
    return redirect(url_for('index'))

@app.route('/onboarding', methods=['GET', 'POST'])
def onboarding():
    if 'usuario' not in session:
        return redirect(url_for('login_view'))
        
    if request.method == 'POST':
        try:
            peso = float(request.form['peso_kg'])
            altura = int(request.form['altura_cm'])
            edad = int(request.form['edad'])
            sexo = request.form['sexo']
            dias_entreno = int(request.form['dias_entreno'])
            objetivo = request.form['objetivo']
            
            _, _, calorias_objetivo = calcular_metricas_usuario(peso, altura, edad, sexo, dias_entreno, objetivo)
            
            email = session['usuario']
            guardar_datos_onboarding(email, peso, altura, edad, sexo, dias_entreno, objetivo, calorias_objetivo)
            
            return redirect(url_for('index'))
        except Exception as e:
            return f"Error al procesar el onboarding: {e}", 400
            
    return render_template('onboarding.html')

@app.route('/configuracion', methods=['GET', 'POST'])
def configuracion():
    if 'usuario' not in session:
        return redirect(url_for('login_view'))
        
    email = session['usuario']
    
    if request.method == 'POST':
        try:
            peso = float(request.form['peso_kg'])
            altura = int(request.form['altura_cm'])
            edad = int(request.form['edad'])
            dias_entreno = int(request.form['dias_entreno'])
            objetivo = request.form['objetivo']
            
            usuario_actual = obtener_usuario_por_email(email)
            sexo_biologico = usuario_actual.get('sexo', 'M')
            
            _, _, calorias_objetivo = calcular_metricas_usuario(peso, altura, edad, sexo_biologico, dias_entreno, objetivo)
            
            guardar_datos_onboarding(email, peso, altura, edad, sexo_biologico, dias_entreno, objetivo, calorias_objetivo)
            
            return redirect(url_for('index'))
        except Exception as e:
            return f"Error al actualizar: {e}", 400
            
    usuario = obtener_usuario_por_email(email)
    return render_template('configuracion.html', user_data=usuario)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_view'))

if __name__ == '__main__':
    app.run(debug=True)