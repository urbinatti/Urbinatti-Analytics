import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from google import genai
from datetime import timedelta
load_dotenv()
from database import (
    init_db, 
    obtener_usuario_por_email, 
    registrar_o_actualizar_usuario_google, 
    guardar_datos_onboarding,
    actualizar_gemini_key,
    descifrar_key
)

app = Flask(__name__)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1000)

app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Falta configurar la SECRET_KEY en el archivo .env")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

with app.app_context():
    init_db()

def calcular_calorias_y_macros_por_objetivo(peso, altura, edad, sexo, dias_entreno, objetivo):
    actividad = 1.55 if dias_entreno >= 4 else 1.375
    
    if sexo.upper() == 'M':
        tmb = (10 * peso) + (6.25 * altura) - (5 * edad) + 5
    else:
        tmb = (10 * peso) + (6.25 * altura) - (5 * edad) - 161

    tdee = tmb * actividad

    if objetivo == 'perdida_agresiva':
        calorias_objetivo = tdee * 0.75  # -25%
    elif objetivo == 'perdida_controlada':
        calorias_objetivo = tdee * 0.85  # -15%
    elif objetivo == 'volumen_limpio':
        calorias_objetivo = tdee * 1.10  # +10%
    elif objetivo == 'volumen_fuerte':
        calorias_objetivo = tdee * 1.20  # +20%
    else:
        calorias_objetivo = tdee  # Mantenimiento

    return round(tdee), round(calorias_objetivo)

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_view'))

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
    
    try:
        token_r = requests.post(token_url, data=token_data)
        token_json = token_r.json()
    except Exception as e:
        return f"Error de conexión con Google Token API: {e}", 500
    
    if "access_token" not in token_json:
        return f"Error al obtener el token de Google: {token_json}", 400
        
    user_info_r = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {token_json['access_token']}"}
    )
    user_info = user_info_r.json()
    
    email = user_info.get('email')
    nombre = user_info.get('name')
    
    if not email:
        return "Error: Google no devolvió un email válido.", 400

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
            
            tdee, calorias_objetivo = calcular_calorias_y_macros_por_objetivo(
                peso, altura, edad, sexo, dias_entreno, objetivo
            )

            email = session['usuario']
            guardar_datos_onboarding(
                email, peso, altura, edad, sexo, dias_entreno, objetivo, calorias_objetivo
            )

            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"Error detallado en onboarding: {e}")
            return f"Error crítico al procesar el onboarding: {e}", 500

    return render_template('onboarding.html')

@app.route('/configuracion', methods=['GET', 'POST'])
def configuracion():
    if 'usuario' not in session:
        return redirect(url_for('login_view'))
        
    email = session['usuario']
    usuario_actual = obtener_usuario_por_email(email)
    
    if request.method == 'POST':
        try:
            peso = float(request.form['peso_kg'])
            altura = int(request.form['altura_cm'])
            edad = int(request.form['edad'])
            dias_entreno = int(request.form['dias_entreno'])
            objetivo = request.form['objetivo']
            gemini_api_key = request.form.get('gemini_api_key', '').strip()
            
            sexo_biologico = usuario_actual.get('sexo', 'M')
            
            tdee, calorias_objetivo = calcular_calorias_y_macros_por_objetivo(
                peso, altura, edad, sexo_biologico, dias_entreno, objetivo
            )
            
            guardar_datos_onboarding(
                email, peso, altura, edad, sexo_biologico, dias_entreno, objetivo, calorias_objetivo
            )
            
            if gemini_api_key:
                actualizar_gemini_key(email, gemini_api_key)
            
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Error al actualizar configuración: {e}")
            return f"Error al actualizar: {e}", 400
            
    return render_template('configuracion.html', user_data=usuario_actual)

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
    
    # Variable en minúsculas
    api_key_cifrada = usuario.get('gemini_api_key')
    
    if not api_key_cifrada or api_key_cifrada.startswith('fit_live_'):
        return {"respuesta": "No tenés configurada tu API key personal de Gemini. Cargala en tu configuración para poder usar el chat."}
    
    # Variable en minúsculas coincidiendo con la función
    api_key_real = descifrar_key(api_key_cifrada)
    
    if not api_key_real:
        return {"respuesta": "Error al descifrar la API key. Verificá tu configuración."}
    
    try:
        client = genai.Client(api_key=api_key_real)
        
        prompt = f"""
        Sos un asistente nutricional personal, estricto, crudo, realista y objetivo, sin proteger sentimientos ni buscar complacer.
        El usuario pesa 70 kg, entrena 5 veces por semana y apunta a un déficit calórico eficiente.
        
        Reglas de comportamiento y negocio obligatorias:
        1. **Manejo de Conversación General:** Si el mensaje del usuario es un saludo (como "hola"), una pregunta general o una charla que no implique la ingesta de un alimento, respondé con naturalidad manteniendo tu tono directo, objetivo y sin intentar calcular macros de algo que no es comida.
        2. **Desglose Nutricional:** Si el usuario describe un alimento o plato, calculá de forma realista y objetiva las calorías, proteínas, carbohidratos y grasas. Presentá la información de forma estructurada y concisa.
        
        Mensaje del usuario: "{mensaje_usuario}"
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        return {"respuesta": response.text}
        
    except Exception as e:
        print(f"Error en chat IA: {e}")
        return {"respuesta": f"Error al procesar con la IA: {str(e)}"}