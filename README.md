# Urbinatti Analytics 📊

> Sistema Full-Stack de seguimiento nutricional automatizado con Inteligencia Artificial, notificaciones asíncronas y arquitectura PWA.

Urbinatti Analytics es una aplicación web progresiva (PWA) diseñada para el cálculo y monitoreo preciso de macronutrientes y déficit calórico. En lugar de requerir que el usuario ingrese datos manualmente en formularios extensos, el sistema utiliza procesamiento de lenguaje natural (NLP) a través de la API de Google Gemini para interpretar comandos cotidianos y extraer métricas nutricionales exactas.
https://urbinatti.pythonanywhere.com/login

## 🚀 Características Principales

*   **Procesamiento de Lenguaje Natural (NLP):** Integración con Google Gemini (GenAI SDK) para interpretar inputs libres (ej: *"Comí 200g de milanesa y una ensalada"*), calculando desgloses finos de calorías, proteínas, carbohidratos y grasas con lógica de negocio predefinida.
*   **Progressive Web App (PWA):** Interfaz instalable en dispositivos móviles, soportada por Service Workers para manejo de caché y ejecución en segundo plano.
*   **Motor de Notificaciones Push Automatizado:** Sistema propio de notificaciones (WebPush/VAPID) enlazado a Cron-jobs externos. Incluye lógica algorítmica para evaluar la ventana de inactividad (3 días) y optimizar los recursos del servidor.
*   **Autenticación Segura (SSO):** Implementación de Google OAuth 2.0 para la gestión de sesiones sin almacenamiento de contraseñas locales.
*   **Criptografía y Seguridad:** Almacenamiento seguro de credenciales de terceros (API Keys de usuarios) mediante encriptación simétrica utilizando la librería `cryptography` (Fernet).
*   **Cálculo Metabólico Dinámico:** Algoritmos integrados para calcular el TDEE (Total Daily Energy Expenditure) basados en biometría, actividad física y objetivos de volumen o déficit.

## 🛠️ Stack Tecnológico

**Backend:**
*   Python 3.x
*   Flask (Framework web)
*   SQLite3 (Base de datos relacional)
*   PyWebPush (Protocolo VAPID)
*   Authlib (Integración OAuth)

**Frontend:**
*   HTML5 & CSS3
*   TailwindCSS (Estilos utilitarios)
*   JavaScript Vanilla (DOM y Service Workers)
*   Marked.js (Renderizado de Markdown en el cliente)

**Cloud & DevOps:**
*   PythonAnywhere (Hosting y Despliegue)
*   Git & GitHub (Control de versiones)
*   Cron-job.org (Automatización de tareas programadas)

## 🏗️ Arquitectura del Sistema

1.  **Capa de Presentación:** UI construida con TailwindCSS, manejando estados dinámicos a través de gráficos SVG y solicitudes asíncronas (Fetch API) al servidor.
2.  **Capa de Autenticación:** El flujo OAuth redirige al proveedor de identidad (Google) y establece una sesión segura mediante cookies firmadas.
3.  **Capa de Lógica (Motor de IA):** El prompt de sistema está diseñado con ingeniería de instrucciones restrictiva para obligar al LLM a responder con un esquema JSON determinista, listo para ser consumido por la base de datos.
4.  **Capa de Persistencia:** Estructura relacional en SQLite para relacionar perfiles de usuario, registros de comidas diarios e historial de conversaciones.

## ⚙️ Instalación y Despliegue Local

Si deseas correr este proyecto en un entorno de desarrollo local:

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/tu-usuario/Urbinatti-Analytics.git](https://github.com/tu-usuario/Urbinatti-Analytics.git)
   cd Urbinatti-Analytics