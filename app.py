import os
import secrets
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import database
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
        return False
    finally:
        cursor.close()
        conn.close()

def obtener_totales_sincronizados(usuario_id):
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT calorias, proteinas, carbohidratos, grasas 
        FROM registros_comidas 
        WHERE usuario_id = ? AND DATE(timestamp) = DATE('now', 'localtime')
    """, (usuario_id,))
    registros = cursor.fetchall()
    cursor.close()
    conn.close()
    
    calorias_totales = sum(float(r['calorias'] or 0) for r in registros)
    proteina_total = sum(float(r['proteinas'] or 0) for r in registros)
    carbs_totales = sum(float(r['carbohidratos'] or 0) for r in registros)
    grasas_totales = sum(float(r['grasas'] or 0) for r in registros)
    
    return {
        'calorias': int(calorias_totales),
        'proteinas': int(proteina_total),
        'carbohidratos': int(carbs_totales),
        'grasas': int(grasas_totales)
    }

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
    api_key_db = str(user_data.get('gemini_api_key') or '').strip()
    tiene_api_key = len(api_key_db) > 20 
        
    cursor.execute("""
        SELECT * FROM registros_comidas 
        WHERE usuario_id = ? AND DATE(timestamp) = DATE('now', 'localtime')
        ORDER BY timestamp DESC
    """, (usuario_id,))
    registros = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    
    totales = obtener_totales_sincronizados(usuario_id)
    
    peso = float(user_data.get('peso_kg') or 70.0)
    dias_gym = int(user_data.get('entrenamientos_semanales') or 5)
    deficit_target = int(user_data.get('deficit_objetivo_kcal') or -500)
    
    meta_calorias = 0
    meta_proteina = 0
    if peso > 0:
        factor_actividad = 1.2 + (dias_gym * 0.07)
        tdee_base = (10 * peso + 625) * factor_actividad
        meta_calorias = int(tdee_base + deficit_target)
        meta_proteina = int(peso * 2.0)

    return render_template(
        'index.html',
        registros=registros,
        user_data=user_data,
        calorias_totales=totales['calorias'],
        proteina_total=totales['proteinas'],
        carbs_totales=totales['carbohidratos'],
        grasas_totales=totales['grasas'],
        meta_calorias=meta_calorias,
        meta_proteina=meta_proteina,
        tiene_api_key=tiene_api_key
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
            flash("Credenciales incorrectas o usuario inexistente.", "error")
            return render_template('login.html')
    return render_template('login.html')

@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    password = request.form.get('password')
    peso = float(request.form.get('peso', 70.0))
    entrenamientos = int(request.form.get('entrenamientos_semanales', 5))
    deficit = int(request.form.get('deficit_calorico', 0))
    
    objetivo = "recomposicion" if -100 <= deficit <= 100 else ("definicion" if deficit < -100 else "volumen")
    resultado = database.registrar_nuevo_usuario(nombre, password, peso, entrenamientos, objetivo, deficit)
    
    if resultado.get('status') == 'success':
        flash("¡Cuenta creada con éxito! Ahora podés iniciar sesión.", "success")
        return redirect(url_for('login'))
        
    flash(f"Error: {resultado.get('message')}", "error")
    return redirect(url_for('login'))

@app.route('/ingreso', methods=['POST'])
def ingreso():
    if 'usuario_id' not in session:
        return jsonify({'status': 'error', 'message': 'Sesión expirada.'}), 401
        
    usuario_id = session['usuario_id']
    data = request.get_json(silent=True) or request.form
    descripcion = data.get('descripcion', '').strip()
    
    if not descripcion:
        return jsonify({'status': 'error', 'message': 'Mensaje vacío.'}), 400
        
    user_api_key = session.get('usuario_api_key')
    
    if not user_api_key:
        return jsonify({'status': 'revoked', 'message': 'No hay API Key activa.'}), 401

    try:
        user_data = obtener_datos_atleta_local(usuario_id)
        peso_cliente = user_data.get('peso_kg', 70.0)
        entrenamientos_cliente = user_data.get('entrenamientos_semanales', 3)
        objetivo_cliente = user_data.get('objetivo', 'mantenimiento')
        
        genai.configure(api_key=user_api_key, transport='rest')
        
        instruccion_sistema = f"Eres un asistente de nutrición y rendimiento deportivo objetivo y directo. El usuario actual pesa {peso_cliente}kg, entrena {entrenamientos_cliente} veces por semana y su objetivo es {objetivo_cliente}. Tu tarea es mantener una charla fluida y útil. Si el usuario menciona que consumió alimentos, estima sus macronutrientes y calorías con precisión. Si es charla general, responde natural y deja la lista vacía."

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

        model = genai.GenerativeModel(model_name="gemini-2.0-flash", system_instruction=instruccion_sistema)
        response = model.generate_content(
            descripcion,
            generation_config=genai.GenerationConfig(response_mime_type="application/json", response_schema=RespuestaIA),
            request_options={"timeout": 15.0}
        )
        
        resultado_ia = json.loads(response.text)
        alimentos = resultado_ia.get('alimentos', [])
        alimentos_procesados = []

        if alimentos and isinstance(alimentos, list):
            conn = database.obtener_conexion()
            cursor = conn.cursor()
            for item in alimentos:
                desc = str(item.get('descripcion') or 'Alimento')
                p_gr, kcal, prot, carb, grasa = float(item.get('peso') or 0.0), float(item.get('calorias') or 0.0), float(item.get('proteinas') or 0.0), float(item.get('carbohidratos') or 0.0), float(item.get('grasas') or 0.0)
                
                cursor.execute("""
                    INSERT INTO registros_comidas (descripcion, peso, calorias, proteinas, carbohidratos, grasas, timestamp, usuario_id)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
                """, (desc, p_gr, kcal, prot, carb, grasa, usuario_id))
                
                alimentos_procesados.append({
                    'id': cursor.lastrowid, 'descripcion': desc, 'calorias': kcal, 
                    'proteinas': prot, 'carbohidratos': carb, 'grasas': grasa, 'timestamp': 'Justo ahora'
                })
            conn.commit()
            cursor.close()
            conn.close()

        totales_sincronizados = obtener_totales_sincronizados(usuario_id)

        return jsonify({
            'status': 'success',
            'respuesta_ia': resultado_ia.get('respuesta_chat', ''),
            'nuevos_alimentos': alimentos_procesados,
            'totales': totales_sincronizados
        })
        
    except Exception as e:
        error_msg = str(e).lower()
        if '429' in error_msg or 'quota' in error_msg:
            return jsonify({'status': 'quota', 'message': 'Límite de cuota excedido en el proyecto GCP.'}), 429
        elif 'api_key_invalid' in error_msg or 'api key not valid' in error_msg or '400' in error_msg or '403' in error_msg:
            database.actualizar_gemini_key(usuario_id, "")
            session.pop('usuario_api_key', None)
            return jsonify({'status': 'revoked', 'message': 'API Key revocada o inhabilitada.'}), 401
            
        return jsonify({'status': 'error', 'message': f'Error del servidor: {str(e)}'}), 500

@app.route('/guardar_api_key', methods=['POST'])
def guardar_api_key():
    usuario_id = session.get('usuario_id')
    if not usuario_id:
        return jsonify({'status': 'error', 'message': 'Sesión desautorizada.'}), 401
    
    data = request.get_json()
    api_key_real = data.get('gemini_api_key', '').strip()
    
    if len(api_key_real) < 15:
        return jsonify({'status': 'error', 'message': 'La clave ingresada es demasiado corta para ser válida.'}), 400
        
    try:
        genai.configure(api_key=api_key_real, transport='rest')
        model = genai.GenerativeModel("gemini-2.0-flash") 
        model.generate_content("ok", request_options={"timeout": 10.0})
    except Exception as e:
        error_msg = str(e).lower()
        if '429' in error_msg or 'quota' in error_msg:
             return jsonify({'status': 'error', 'message': 'La clave es real, pero el proyecto GCP asociado tiene cuota en 0.'}), 400
        return jsonify({'status': 'error', 'message': f'La API Key es inválida o fue rechazada. Detalle: {str(e)}'}), 400

    exito = database.actualizar_gemini_key(usuario_id, api_key_real)
    if exito:
        session['usuario_api_key'] = api_key_real
        return jsonify({'status': 'success', 'message': 'API Key verificada y vinculada.'})
        
    return jsonify({'status': 'error', 'message': 'Error interno al escribir en la base de datos.'}), 500

@app.route('/borrar_comida/<int:comida_id>', methods=['POST', 'DELETE'])
def borrar_comida(comida_id):
    if 'usuario_id' not in session:
        return jsonify({'status': 'error', 'message': 'No autorizado.'}), 401
        
    usuario_id = session['usuario_id']
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros_comidas WHERE id = ? AND usuario_id = ?", (comida_id, usuario_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    totales_sincronizados = obtener_totales_sincronizados(usuario_id)
    return jsonify({'status': 'success', 'totales': totales_sincronizados})

@app.route('/actualizar_objetivos', methods=['POST'])
def actualizar_objetivos():
    usuario_id = session.get('usuario_id')
    if not usuario_id:
        return jsonify({'status': 'error', 'message': 'Sesión no válida.'}), 401
        
    data = request.get_json()
    peso, entrenamientos, deficit_ingresado = float(data.get('peso', 70.0)), int(data.get('entrenamientos_semanales', 5)), int(data.get('deficit_calorico', 0))
    objetivo = "recomposicion" if -100 <= deficit_ingresado <= 100 else ("definicion" if deficit_ingresado < -100 else "volumen")
    
    if modificar_perfil_atleta_local(usuario_id, peso, entrenamientos, objetivo, deficit_ingresado):
        return jsonify({'status': 'success', 'message': 'Variables sincronizadas.'})
    return jsonify({'status': 'error', 'message': 'Fallo en la base de datos.'}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)