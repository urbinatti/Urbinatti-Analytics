import os
import secrets
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import database
import requests


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(24))

# =====================================================================
# FUNCIONES LOCALES DE BASE DE DATOS
# =====================================================================

def obtener_datos_atleta_local(usuario_id):
    conn = database.obtener_conexion() 
    if not conn: 
        return {'peso': 70.0, 'entrenamientos': 5, 'objetivo': 'definicion', 'deficit': -500}
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT peso_kg, entrenamientos_semanales, deficit_objetivo_kcal FROM usuarios WHERE id = %s", (usuario_id,))
        res = cursor.fetchone()
        if res:
            return {
                'peso': res['peso_kg'],
                'entrenamientos': res['entrenamientos_semanales'],
                'deficit': res['deficit_objetivo_kcal']
            }
        return {'peso': 70.0, 'entrenamientos': 5, 'deficit': -500}
    except Exception as e:
        print(f"[LOCAL ERROR OBTENER ATLETA]: {e}")
        return {'peso': 70.0, 'entrenamientos': 5, 'deficit': -500}
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
            SET peso_kg = %s, entrenamientos_semanales = %s, deficit_objetivo_kcal = %s 
            WHERE id = %s
        """, (peso, entrenamientos, deficit, usuario_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[LOCAL UPDATE ERROR]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def obtener_totales_hoy_local(usuario_id):
    conn = database.obtener_conexion()
    if not conn: 
        return {'calorias': 0, 'proteinas': 0, 'carbohidratos': 0, 'grasas': 0}
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                IFNULL(SUM(calorias), 0) as calorias, 
                IFNULL(SUM(proteinas), 0) as proteinas, 
                IFNULL(SUM(carbohidratos), 0) as carbohidratos, 
                IFNULL(SUM(grasas), 0) as grasas 
            FROM registros_comidas 
            WHERE usuario_id = %s AND DATE(timestamp) = CURDATE()
        """, (usuario_id,))
        return cursor.fetchone() or {'calorias': 0, 'proteinas': 0, 'carbohidratos': 0, 'grasas': 0}
    except Exception as e:
        print(f"[LOCAL TOTALS ERROR]: {e}")
        return {'calorias': 0, 'proteinas': 0, 'carbohidratos': 0, 'grasas': 0}
    finally:
        cursor.close()
        conn.close()

def obtener_registros_hoy_local(usuario_id):
    conn = database.obtener_conexion()
    if not conn: return []
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT descripcion, calorias, proteinas, carbohidratos, grasas, DATE_FORMAT(timestamp, '%H:%i') as timestamp 
            FROM registros_comidas 
            WHERE usuario_id = %s AND DATE(timestamp) = CURDATE()
            ORDER BY id DESC
        """, (usuario_id,))
        return cursor.fetchall() or []
    except Exception as e:
        print(f"[LOCAL HISTORY ERROR]: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

# =====================================================================
# RUTAS DE LA APLICACIÓN
# =====================================================================

@app.route('/')
def index():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    
    # 1. Consultar perfil de usuario directo de la DB
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        cursor.close()
        conn.close()
        return "Error: Usuario no encontrado.", 404
        
    # 2. Consultar registros de comidas de HOY
    cursor.execute("""
        SELECT * FROM registros_comidas 
        WHERE usuario_id = %s AND DATE(timestamp) = CURDATE()
        ORDER BY timestamp DESC
    """, (usuario_id,))
    registros = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 3. Métricas y totales consumidos
    calorias_totales = sum(int(r.get('calorias') or 0) for r in registros)
    proteina_total = sum(int(r.get('proteinas') or 0) for r in registros)
    carbs_totales = sum(int(r.get('carbohidratos') or 0) for r in registros)
    grasas_totales = sum(int(r.get('grasas') or 0) for r in registros)
    
    # 4. Cálculo metabólico exacto basado en las columnas reales de DB
    peso = float(user_data.get('peso_kg') or 0)
    dias_gym = int(user_data.get('entrenamientos_semanales') or 0)
    deficit_target = int(user_data.get('deficit_objetivo_kcal') or 0)
    
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

    # 5. Envío directo al template
    return render_template(
        'index.html',
        registros=registros,
        user_data=user_data,
        calorias_totales=calorias_totales,
        proteina_total=proteina_total,
        carbs_totales=carbs_totales,
        grasas_totales=grasas_totales,
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
    
    resultado = database.registrar_nuevo_usuario(nombre, password, peso, entrenamientos, objective=objetivo, deficit=deficit)
    
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
        return "Error: No hay API Key activa.", 400

    try:
        user_data = obtener_datos_atleta_local(usuario_id)
        peso_actual = user_data.get('peso', 70.0)
        
        prompt_sistema = f"""Actúas como un software de nutrición y rendimiento deportivo. El usuario pesa {peso_actual}kg.
REGLAS:
1. Si el usuario describe comidas consumidas, desglosa CADA ALIMENTO en "alimentos".
2. Si menciona huesos, réstalos del peso total.
3. Si el usuario pide BORRAR o ELIMINAR una comida (ej: "borra el hola", "elimina la pata de pollo"), clasifica tipo = "borrar" y en "patron_borrar" pon el texto o alimento a eliminar.
4. Para consultas o saludos, tipo = "chat".

Devuelve EXCLUSIVAMENTE este JSON:
{{
  "tipo": "comida" | "borrar" | "chat",
  "patron_borrar": "texto o nombre a borrar o null",
  "alimentos": [
    {{
      "alimento": "Nombre limpio del alimento",
      "calorias": numero_entero,
      "proteinas": numero_entero,
      "carbohidratos": numero_entero,
      "grasas": numero_entero
    }}
  ],
  "respuesta_chat": "Respuesta si es chat o null"
}}"""

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={user_api_key}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": [{"text": prompt_sistema}, {"text": f"Mensaje: {descripcion}"}]}]}
        
        response = requests.post(url, headers=headers, json=payload)
        res_data = response.json()
        
        texto_crudo = res_data['candidates'][0]['content']['parts'][0]['text']
        texto_limpio = texto_crudo.replace('```json', '').replace('```', '').strip()
        resultado_ia = json.loads(texto_limpio)
        
        tipo_intencion = resultado_ia.get('tipo')
        
        # 1. CASO REGISTRO DE COMIDAS MULTIPLES
        if tipo_intencion == 'comida' and resultado_ia.get('alimentos'):
            conn = database.obtener_conexion()
            cursor = conn.cursor()
            total_kcal = 0
            
            for item in resultado_ia.get('alimentos', []):
                nombre = item.get('alimento', 'Alimento')
                kcal = int(item.get('calorias') or 0)
                cursor.execute("""
                    INSERT INTO registros_comidas (usuario_id, descripcion, calorias, proteinas, carbohidratos, grasas)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (usuario_id, nombre, kcal, int(item.get('proteinas') or 0), int(item.get('carbohidratos') or 0), int(item.get('grasas') or 0)))
                total_kcal += kcal
                
            conn.commit()
            cursor.close()
            conn.close()
            session['respuesta_ia_chat'] = f"✅ Registrados {len(resultado_ia['alimentos'])} ítems desglosados ({total_kcal} kcal)."

        # 2. CASO BORRADO POR IA
        elif tipo_intencion == 'borrar' and resultado_ia.get('patron_borrar'):
            patron = f"%{resultado_ia.get('patron_borrar')}%"
            conn = database.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM registros_comidas WHERE usuario_id = %s AND descripcion LIKE %s", (usuario_id, patron))
            filas_borradas = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            
            if filas_borradas > 0:
                session['respuesta_ia_chat'] = f"🗑️ Se eliminaron {filas_borradas} registro(s) que coincidían con '{resultado_ia.get('patron_borrar')}'."
            else:
                session['respuesta_ia_chat'] = f"⚠️ No se encontró ningún registro que coincida con '{resultado_ia.get('patron_borrar')}'."

        # 3. CASO CHAT GENERAL
        else:
            session['respuesta_ia_chat'] = resultado_ia.get('respuesta_chat', 'Entendido.')

        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"[ERROR INGESTA]: {e}")
        return f"Error: {e}", 500

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
        
    return jsonify({'status': 'error', 'message': 'Error interno al escribir en MySQL.'}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# NUEVA RUTA PARA BORRADO MANUAL CON BOTÓN
@app.route('/borrar_comida/<int:comida_id>', methods=['POST'])
def borrar_comida(comida_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros_comidas WHERE id = %s AND usuario_id = %s", (comida_id, usuario_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    session['respuesta_ia_chat'] = "🗑️ Registro eliminado correctamente."
    return redirect(url_for('index'))

# =====================================================================
# ARRANQUE DEL SERVIDOR (SIEMPRE AL FINAL DEL ARCHIVO)
# =====================================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)