# -*- coding: utf-8 -*-
import os
import json
import hashlib
import requests
from flask import request, redirect, url_for, render_template, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from app import app, IA_SERVER, IA_URL, IA_STATUS_URL, IA_VIDEO_URL
from utils import allowed_file, log_print, cleanup_old_files

TRUEREP_API_KEY = os.environ.get('TRUEREP_API_KEY', 'truerep_internal_token_v1')
API_KEY_HEADER = {'X-API-KEY': TRUEREP_API_KEY}
ALLOWED_EXERCISES = ('squat', 'pushup', 'pullup')
ALLOWED_LEVELS = ('standard', 'strict')


@app.route('/')
def root_redirect():
    return redirect(url_for('index_form'), code=302)


@app.route('/truerep/')
def index_form():
    return render_template('index.html')


@app.route('/truerep/upload', methods=['POST'])
def upload_video():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se envió ningún archivo de video.'}), 400

        file = request.files['file']
        exercise = request.form.get('exercise', 'squat')
        if exercise not in ALLOWED_EXERCISES:
            exercise = 'squat'

        level = request.form.get('level', 'standard')
        if level not in ALLOWED_LEVELS:
            level = 'standard'

        if not file or file.filename == '':
            return jsonify({'error': 'No se seleccionó ningún archivo.'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Formato no permitido. Usa MP4, MOV, AVI o WEBM.'}), 400

        file_bytes = file.read()
        log_print("recibo {} bytes (ejercicio: {}, nivel: {})".format(len(file_bytes), exercise, level))

        base_dir = app.config['UPLOAD_FOLDER']
        os.makedirs(base_dir, exist_ok=True)

        md5sum = hashlib.md5(file_bytes).hexdigest()
        filename = md5sum + '_' + secure_filename(file.filename)
        filepath = os.path.join(base_dir, filename)

        log_print("guardando archivo " + filepath)
        with open(filepath, "wb") as f:
            f.write(file_bytes)

        files = {'file': (filename, file_bytes, file.mimetype or 'video/mp4')}
        data = {'exercise': exercise, 'level': level}

        log_print("llamando a " + IA_SERVER + IA_URL)
        apicall = requests.post(
            IA_SERVER + IA_URL,
            files=files,
            data=data,
            timeout=(5, 600),
            headers=API_KEY_HEADER,
        )

        if apicall.status_code != 200:
            return jsonify({'error': 'Error contactando el módulo IA (código {}).'.format(apicall.status_code)}), 502

        api_json = json.loads(apicall.content.decode('utf-8'))

        # Descargar el video con el esqueleto renderizado hacia static/uploads/ para servirlo localmente
        processed_name = api_json.get('video_procesado')
        if processed_name:
            vid_resp = requests.get(IA_SERVER + IA_VIDEO_URL + processed_name, timeout=(5, 120))
            if vid_resp.status_code == 200:
                local_vid_path = os.path.join(base_dir, processed_name)
                with open(local_vid_path, 'wb') as vf:
                    vf.write(vid_resp.content)
                api_json['video_url'] = url_for('serve_video', filename=processed_name)

        cleanup_old_files(base_dir, max_files=10)
        return jsonify(api_json)
    except Exception as e:
        error_msg = "Error: {}".format(e)
        log_print(error_msg)
        return jsonify({'error': error_msg}), 500


@app.route('/truerep/status', methods=['GET'])
def check_status():
    try:
        resp = requests.get(IA_SERVER + IA_STATUS_URL, timeout=2)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception:
        pass
    return jsonify({'stage': 'pose', 'percent': 10, 'message': 'Procesando video...'})


@app.route('/truerep/videos/<filename>')
def serve_video(filename):
    safe_filename = secure_filename(filename)
    abs_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
    return send_from_directory(abs_folder, safe_filename, mimetype='video/mp4', conditional=True)


if __name__ == "__main__":
    app.run(port=7001, threaded=True, use_reloader=True)
