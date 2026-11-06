# -*- coding: utf-8 -*-
import os
from flask import Flask

# puerto 7002 es usado para desarrollo en __main__
IA_SERVER = os.environ.get('IA_SERVER', 'http://127.0.0.1:7002')

IA_URL = '/api/v1/analyze'
IA_STATUS_URL = '/api/v1/analysis/status'
IA_VIDEO_URL = '/api/v1/videos/'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

app = Flask(__name__,
            static_url_path='/truerep/static')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['TEMPLATES_AUTO_RELOAD'] = True
