# -*- coding: utf-8 -*-
import os
import threading
from datetime import datetime

ALLOWED_EXTENSIONS = set(['mp4', 'mov', 'avi', 'webm'])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def log_print(message):
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    thread_id = threading.get_ident()
    prefijo = f"[{time_str}] [{thread_id}]"
    print(prefijo, message)


def cleanup_old_files(folder_path, max_files=10):
    """Conserva únicamente los `max_files` archivos más recientes en `folder_path`."""
    if not os.path.isdir(folder_path):
        return
    files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if not f.startswith('.') and os.path.isfile(os.path.join(folder_path, f))
    ]
    if len(files) <= max_files:
        return
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for old_path in files[max_files:]:
        try:
            os.remove(old_path)
        except OSError:
            pass
