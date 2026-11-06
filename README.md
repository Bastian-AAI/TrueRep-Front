# TrueRep-Front

Módulo frontend en Flask para **TrueRep**, Analizador Biomecánico y Contador de Repeticiones para **Sentadilla (Squat)**, **Flexiones (Push-up)** y **Dominadas (Pull-up)**.

## Instalación

```bash
pip install -r requirements.txt
```

## Variables de Entorno

- `IA_SERVER`: URL del backend de TrueRep-IA (por defecto: `http://127.0.0.1:7002`).
- `TRUEREP_API_KEY`: Clave de autenticación para comunicarse con TrueRep-IA (por defecto: `truerep_internal_token_v1`).

## Ejecución

```bash
python main.py
```

- La interfaz web está disponible en: `http://127.0.0.1:7001/truerep/` (con redirección automática desde `http://127.0.0.1:7001/`).

## Rutas del Servicio

- `GET /`: Redirige (302) a `/truerep/`.
- `GET /truerep/`: Vista principal web con interfaz interactiva de análisis y carga de videos.
- `POST /truerep/upload`: Endpoint receptor para carga de video e invocación de inferencia a TrueRep-IA.
- `GET /truerep/status`: Proxy de consulta de progreso en tiempo real.
- `GET /truerep/videos/<filename>`: Entrega del video procesado con el esqueleto superpuesto.
- `GET /truerep/static/...`: Recursos estáticos (CSS, JS, logos).
