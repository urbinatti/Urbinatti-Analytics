import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env (que está oculto y no se sube a GitHub)
load_dotenv()

app = Flask(__name__)

# Se extrae estrictamente de la variable de entorno protegida
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Falta configurar la SECRET_KEY en el archivo .env")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login_view'))
    
    # Objeto con los datos que la plantilla index.html está exigiendo
    user_data = {
        "peso_kg": 70
    }
    
    return render_template('index.html', user_data=user_data)
@app.route('/login', methods=['GET', 'POST'])
def login_view():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        password = request.form.get('password')
        session['usuario'] = nombre
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    password = request.form.get('password')
    peso = request.form.get('peso')
    entrenamientos = request.form.get('entrenamientos_semanales')
    deficit = request.form.get('deficit_calorico')
    
    session['usuario'] = nombre
    return redirect(url_for('index'))

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
    
    session['usuario'] = user_info.get('email')
    session['nombre'] = user_info.get('name')
    
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_view'))

if __name__ == '__main__':
    app.run(debug=True)