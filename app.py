import os
import secrets
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import database
import requests
import google.generativeai as genai
import typing_extensions as typing

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(24))

def obtener_datos_atleta_local(usuario_id):
    conn = database.obtener_conexion() 
    if not conn: 
        return {'peso_kg': 70.0, 'entrenamientos_semanales': 5, 'deficit_objetivo_kcal': -500}
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT peso_kg, entrenamientos_semanales, deficit_objetivo_kcal FROM usuarios WHERE id = ?", (usuario_id,))
        res = cursor.fetchone()
        if res:
            return dict(res)
        return {'peso_kg': 70.0, 'entrenamientos_semanales': 5, 'deficit_objetivo_kcal': -500}
    except Exception as e:
        print(f"[LOCAL ERROR OBTENER ATLETA]: {e}")
        return {'peso_kg': 70.0, 'entrenamientos_semanales': 5, 'deficit_objetivo_kcal': -500}
    finally:
        cursor.close()
        conn.close()

def modificar_perfil_atleta_local(usuario_id, peso, entrenamientos, objetivo, deficit):
    conn = database.obtener_conexion()
    if not conn: return False
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE usuarios 
            SET peso_kg = ?, entrenamientos_semanales = ?, deficit_objetivo_kcal = ? 
            WHERE id = ?
        """, (peso, entrenamientos, deficit, usuario_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[LOCAL UPDATE ERROR]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

@app.route('/')
def index():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row_user = cursor.fetchone()
    
    if not row_user:
        cursor.close()
        conn.close()
        return "Error: Usuario no encontrado.", 404
        
    user_data = dict(row_user)
        
    cursor.execute("""
        SELECT * FROM registros_comidas 
        WHERE usuario_id = ? AND DATE(timestamp) = DATE('now', 'localtime')
        ORDER BY timestamp DESC
    """, (usuario_id,))
    registros = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    
    calorias_totales = sum(float(r.get('calorias') or 0) for r in registros)
    proteina_total = sum(float(r.get('proteinas') or 0) for r in registros)
    carbs_totales = sum(float(r.get('carbohidratos') or 0) for r in registros)
    grasas_totales = sum(float(r.get('grasas') or 0) for r in registros)
    
    peso = float(user_data.get('peso_kg') or 70.0)
    dias_gym = int(user_data.get('entrenamientos_semanales') or 5)
    deficit_target = int(user_data.get('deficit_objetivo_kcal') or -500)
    
    if peso > 0:
        factor_actividad = 1.2 + (dias_gym * 0.07)
        tdee_base = (10 * peso + 625) * factor_actividad
        meta_calorias = int(tdee_base + deficit_target)
        meta_proteina = int(peso * 2.0)
    else:
        meta_calorias = 0
        meta_proteina = 0
    
    margen_calorias = meta_calorias - calorias_totales
    margen_proteina = meta_proteina - proteina_total

    return render_template(
        'index.html',
        registros=registros,
        user_data=user_data,
        calorias_totales=int(calorias_totales),
        proteina_total=int(proteina_total),
        carbs_totales=int(carbs_totales),
        grasas_totales=int(grasas_totales),
        meta_calorias=meta_calorias,
        meta_proteina=meta_proteina,
        margen_calorias=margen_calorias,
        margen_proteina=margen_proteina
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        password = request.form.get('password')
        
        usuario = database.verificar_credenciales(nombre, password)
        if usuario:
            session['usuario_id'] = usuario['id']
            session['usuario_nombre'] = usuario['nombre']
            session['usuario_api_key'] = usuario.get('gemini_api_key')
            return redirect(url_for('index'))
        else:
            return "Credenciales incorrectas", 401
            
    return render_template('login.html')

@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    password = request.form.get('password')
    peso = float(request.form.get('peso', 70.0))
    entrenamientos = int(request.form.get('entrenamientos_semanales', 5))
    deficit = int(request.form.get('deficit_calorico', 0))
    
    if deficit >= -100 and deficit <= 100:
        objetivo = "recomposicion"
    elif deficit < -100:
        objetivo = "definicion"
    else:
        objetivo = "volumen"
    
    resultado = database.registrar_nuevo_usuario(nombre, password, peso, entrenamientos, objetivo, deficit)
    
    if resultado.get('status') == 'success':
        return redirect(url_for('login'))
    return f"Error al registrar: {resultado.get('message')}", 400

@app.route('/ingreso', methods=['POST'])
def ingreso():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    descripcion = request.form.get('descripcion', '').strip()
    
    if not descripcion:
        return redirect(url_for('index'))
        
    session['ultimo_mensaje_usuario'] = descripcion
    user_api_key = session.get('usuario_api_key') or os.environ.get("GEMINI_API_KEY")
    
    if not user_api_key:
        return "Error: No hay API Key activa configurada para este usuario.", 400

    try:
        # Obtenemos los datos dinámicos del cliente actual
        user_data = obtener_datos_atleta_local(usuario_id)
        peso_cliente = user_data.get('peso_kg', 70.0)
        entrenamientos_cliente = user_data.get('entrenamientos_semanales', 3)
        objetivo_cliente = user_data.get('objetivo', 'mantenimiento')
        
        # LA CLAVE PARA PYTHONANYWHERE: forzamos el uso de REST en vez de gRPC
        genai.configure(api_key=user_api_key, transport='rest')
        
        # Prompt dinámico y genérico
        instruccion_sistema = f"""Eres un asistente de nutrición y rendimiento deportivo objetivo y directo. 
El usuario actual pesa {peso_cliente}kg, entrena {entrenamientos_cliente} veces por semana y su objetivo es {objetivo_cliente}. 
Tu tarea es mantener una charla fluida y útil. Si el usuario menciona que consumió alimentos, estima sus macronutrientes y calorías con precisión. Si es una pregunta o charla general, responde de forma natural y deja la lista de alimentos vacía."""

        # Estructura inquebrantable
        class Alimento(typing.TypedDict):
            descripcion: str
            peso: float
            calorias: float
            proteinas: float
            carbohidratos: float
            grasas: float

        class RespuestaIA(typing.TypedDict):
            alimentos: list[Alimento]
            respuesta_chat: str

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=instruccion_sistema
        )
        
        # SEGUNDA CLAVE: Timeout de 15 segundos para que la web nunca se congele
        response = model.generate_content(
            descripcion,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=RespuestaIA,
            ),
            request_options={"timeout": 15.0}
        )
        
        resultado_ia = json.loads(response.text)
        
        # Inserción en BD
        alimentos = resultado_ia.get('alimentos', [])
        if alimentos and isinstance(alimentos, list):
            conn = database.obtener_conexion()
            cursor = conn.cursor()
            for item in alimentos:
                desc = str(item.get('descripcion') or 'Alimento')
                p_gr = float(item.get('peso') or 0.0)
                kcal = float(item.get('calorias') or 0.0)
                prot = float(item.get('proteinas') or 0.0)
                carb = float(item.get('carbohidratos') or 0.0)
                grasa = float(item.get('grasas') or 0.0)
                
                cursor.execute("""
                    INSERT INTO registros_comidas (descripcion, peso, calorias, proteinas, carbohidratos, grasas, timestamp, usuario_id)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
                """, (desc, p_gr, kcal, prot, carb, grasa, usuario_id))
            conn.commit()
            cursor.close()
            conn.close()

        session['respuesta_ia_chat'] = resultado_ia.get('respuesta_chat', 'Proceso completado.')
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"[ERROR CRITICO INGESTA]: {str(e)}")
        session['respuesta_ia_chat'] = f"Error en el servidor al procesar el mensaje con la IA. Detalle técnico: {str(e)}"
        return redirect(url_for('index'))

@app.route('/actualizar_objetivos', methods=['POST'])
def actualizar_objetivos():
    usuario_id = session.get('usuario_id')
    if not usuario_id:
        return jsonify({'status': 'error', 'message': 'Sesión no válida.'}), 401
        
    data = request.get_json()
    peso = float(data.get('peso', 70.0))
    entrenamientos = int(data.get('entrenamientos_semanales', 5))
    deficit_ingresado = int(data.get('deficit_calorico', 0))
    
    if deficit_ingresado >= -100 and deficit_ingresado <= 100:
        objetivo = "recomposicion"
    elif deficit_ingresado < -100:
        objetivo = "definicion"
    else:
        objetivo = "volumen"
    
    exito = modificar_perfil_atleta_local(usuario_id, peso, entrenamientos, objetivo, deficit_ingresado)
    if exito:
        return jsonify({'status': 'success', 'message': 'Variables de rendimiento sincronizadas con éxito.'})
    return jsonify({'status': 'error', 'message': 'No se pudo guardar en la base de datos.'}), 500

@app.route('/guardar_api_key', methods=['POST'])
def guardar_api_key():
    usuario_id = session.get('usuario_id')
    if not usuario_id:
        return jsonify({'status': 'error', 'message': 'Sesión desautorizada.'}), 401
    
    data = request.get_json()
    api_key_real = data.get('gemini_api_key', '').strip()
    
    if not api_key_real:
        return jsonify({'status': 'error', 'message': 'La clave no puede estar vacía.'}), 400
        
    exito = database.actualizar_gemini_key(usuario_id, api_key_real)
    if exito:
        session['usuario_api_key'] = api_key_real
        return jsonify({'status': 'success', 'message': 'API Key enlazada de forma correcta.'})
        
    return jsonify({'status': 'error', 'message': 'Error interno al escribir en la base de datos.'}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/borrar_comida/<int:comida_id>', methods=['POST'])
def borrar_comida(comida_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros_comidas WHERE id = ? AND usuario_id = ?", (comida_id, usuario_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    session['respuesta_ia_chat'] = "🗑️ Registro eliminado correctamente."
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)