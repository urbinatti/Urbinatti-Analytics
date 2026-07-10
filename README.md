# Analytics Fitness Dashboard v1.0
## Sistema Operativo de Auditoría Nutricional y Control de Cargas Físicas con Inteligencia Artificial

Este proyecto es un Dashboard de analítica personal desarrollado en Python (Flask) y SQLite, integrado con la API de Google Gemini para la automatización del procesamiento del lenguaje natural (NLP). El sistema opera bajo un enfoque estricto de auditoría de control metabólico y registro cronológico de entrenamiento adaptado al huso horario de Argentina.

### 📁 Arquitectura del Sistema
*   `app.py`: Backend principal, ruteo de endpoints HTTP, manejo de transacciones e inyección de contexto dinámico a la IA (Function Calling).
*   `database.py`: Motor relacional (SQLite3). Centraliza las consultas agregadas utilizando funciones de ventana y unificación de estructuras de datos heredadas mediante `COALESCE`.
*   `templates/index.html`: Interfaz de usuario (UI) responsiva diseñada para el monitoreo operativo en tiempo real.

### 📊 Características Técnicas Clave
*   **Procesamiento NLP con Reglas de Negocio Estrictas:** La IA procesa entradas complejas de alimentos aplicando fórmulas algorítmicas de composición en tiempo real (por ejemplo, el ratio exacto de segregación para alimentos rebozados: 48.5% proteína magra y 51.5% carbohidratos/lípidos con absorción de aceite).
*   **Persistencia y Unificación de Esquemas (SQL):** Mitigación de deuda técnica en base de datos mediante la convivencia integrada de columnas mediante álgebra relacional (`COALESCE`), permitiendo actualizaciones asíncronas del backend sin pérdida de datos históricos.
*   **Sincronización Cronológica Estricta:** Implementación del manejo de zonas horarias (`zoneinfo`) forzado en el servidor de producción para garantizar el reinicio operativo de las métricas diarias exactamente a las 00:00 del huso local (America/Argentina/Cordoba), manteniendo los logs de entrenamiento de forma persistente.
