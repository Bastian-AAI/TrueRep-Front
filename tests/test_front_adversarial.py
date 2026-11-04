# -*- coding: utf-8 -*-
"""
Empirical Adversarial Test Suite for TrueRep-Front Pull-Up Integration (Milestone 3).
Target Path: TrueRep-Front/tests/test_front_adversarial.py

Categories:
1. Malformed, hostile, and unexpected form inputs in /upload (empty, huge, SQLi, XSS, null bytes, non-ASCII).
2. Video upload boundary conditions (0-byte, corrupted headers, disallowed double extensions, uppercase extensions, path traversal, oversized).
3. Mock TrueRep-IA edge responses (HTTP 500/502/503/504/400, timeouts, connection errors, malformed/truncated JSON, empty reps, extreme metrics, download failures).
4. Jinja2 template rendering under unexpected context variables and DOM integrity.
5. CSS media queries, responsive grid rules, selector validity, and delimiter balancing.
6. Auxiliary routes and utility robustness (/status, /display, cleanup_old_files).
"""

import io
import os
import sys
import json
import re
import requests
import pytest
from unittest.mock import patch, MagicMock

# Ensure TrueRep-Front is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(CURRENT_DIR) == 'tests':
    FRONT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
else:
    FRONT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "..", "TrueRep-Front"))
if FRONT_DIR not in sys.path:
    sys.path.insert(0, FRONT_DIR)

import main
from app import app, IA_SERVER, IA_URL, IA_STATUS_URL, IA_VIDEO_URL
from utils import allowed_file, cleanup_old_files


@pytest.fixture
def client(tmp_path):
    """Configures Flask test client with an isolated temporary uploads directory."""
    test_upload_folder = str(tmp_path / "adversarial_uploads")
    os.makedirs(test_upload_folder, exist_ok=True)

    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = test_upload_folder

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def sample_video():
    """Returns a valid dummy MP4 stream."""
    content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free"
    return io.BytesIO(content), "pullup_valid.mp4"


@pytest.fixture
def base_ia_success_response():
    """Returns a baseline valid JSON response from TrueRep-IA."""
    return {
        "ejercicio": "pullup",
        "ejercicio_nombre": "Dominadas (Pull-up)",
        "nivel": "standard",
        "nivel_nombre": "Est\u00e1ndar Deportivo",
        "repeticiones_validas": 3,
        "intentos_totales": 4,
        "repeticiones_invalidas": 1,
        "duracion_video": 18.0,
        "tiempo_procesamiento": 6.5,
        "diagnostico_general": "Desempe\u00f1o correcto con ligera oscilaci\u00f3n.",
        "repeticiones": [
            {
                "numero": 1,
                "valida": True,
                "motivo": "Repetici\u00f3n v\u00e1lida",
                "fallos": [],
                "start_time": 1.0,
                "end_time": 4.0,
                "timestamp": 2.5,
                "angulo_inflexion": 45.0,
                "angulo_extension": 162.0,
                "angulo_postura": 10.0
            }
        ],
        "video_procesado": None
    }


# ============================================================================
# 1. MALFORMED, HOSTILE, AND UNEXPECTED FORM INPUTS (/upload)
# ============================================================================

@pytest.mark.parametrize("hostile_exercise", [
    "",                                     # Empty string
    "   ",                                  # Whitespace only
    "PULLUP",                               # Uppercase (not exact match)
    "pullup ",                              # Trailing whitespace
    "\tpullup\n",                           # Tab / newline
    "pullup'; DROP TABLE reps; --",         # SQL injection
    "<script>alert('xss')</script>",        # XSS vector
    "pullup\x00malicious",                  # Null byte injection
    "dominadas_\U0001F525_pullup",          # Unicode emoji
    "A" * 100000,                           # 100KB huge string
    "__proto__",                            # Prototype pollution probe
    "undefined",                            # JS literal
    "NaN",                                  # Numeric literal
])
@patch('requests.post')
def test_adversarial_exercise_sanitization_fallback(mock_post, client, sample_video, base_ia_success_response, hostile_exercise):
    """Hostile, malformed, or unexpected exercise values must safely fallback to 'squat'."""
    stream, filename = sample_video
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (stream, filename, 'video/mp4'),
            'exercise': hostile_exercise,
            'level': 'standard'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    forwarded_data = mock_post.call_args[1]['data']
    assert forwarded_data['exercise'] == 'squat', f"Hostile exercise {hostile_exercise!r} did not fallback to 'squat'"


@pytest.mark.parametrize("hostile_level", [
    "",                                     # Empty string
    "   ",                                  # Whitespace
    "STRICT",                               # Uppercase
    "strict ",                              # Trailing whitespace
    "strict'; DELETE FROM config; --",      # SQL injection
    "<img src=x onerror=alert(1)>",         # XSS vector
    "strict\x00evil",                       # Null byte
    "est\u00e1ndar_deportivo",              # Spanish unicode
    "B" * 100000,                           # 100KB huge string
])
@patch('requests.post')
def test_adversarial_level_sanitization_fallback(mock_post, client, sample_video, base_ia_success_response, hostile_level):
    """Hostile, malformed, or unexpected level values must safely fallback to 'standard'."""
    stream, filename = sample_video
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (stream, filename, 'video/mp4'),
            'exercise': 'pullup',
            'level': hostile_level
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    forwarded_data = mock_post.call_args[1]['data']
    assert forwarded_data['level'] == 'standard', f"Hostile level {hostile_level!r} did not fallback to 'standard'"


@patch('requests.post')
def test_adversarial_extraneous_form_parameters_ignored(mock_post, client, sample_video, base_ia_success_response):
    """Extraneous or malicious form parameters must be ignored and not forwarded."""
    stream, filename = sample_video
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (stream, filename, 'video/mp4'),
            'exercise': 'pullup',
            'level': 'strict',
            'admin': 'true',
            'debug': '1',
            '__proto__': 'polluted',
            'override_url': 'http://attacker.com'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    forwarded_data = mock_post.call_args[1]['data']
    assert set(forwarded_data.keys()) == {'exercise', 'level'}
    assert forwarded_data['exercise'] == 'pullup'
    assert forwarded_data['level'] == 'strict'


def test_adversarial_non_multipart_content_type(client):
    """POST /upload with application/json or empty body must return 400 Bad Request."""
    res1 = client.post(
        '/ejercicio2/app2-front/upload',
        data=json.dumps({'exercise': 'pullup'}),
        content_type='application/json'
    )
    assert res1.status_code == 400
    assert 'error' in res1.get_json()

    res2 = client.post('/ejercicio2/app2-front/upload', data='', content_type='text/plain')
    assert res2.status_code == 400
    assert 'error' in res2.get_json()


# ============================================================================
# 2. VIDEO UPLOAD BOUNDARY CONDITIONS (/upload)
# ============================================================================

@patch('requests.post')
def test_adversarial_upload_zero_byte_file(mock_post, client, base_ia_success_response):
    """Uploading a 0-byte video must be processed without unhandled exception in TrueRep-Front."""
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    zero_stream = io.BytesIO(b"")
    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (zero_stream, 'empty_test.mp4'),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    assert mock_post.called
    saved_empty = os.path.join(app.config['UPLOAD_FOLDER'], f"{'d41d8cd98f00b204e9800998ecf8427e'}_empty_test.mp4")
    assert os.path.isfile(saved_empty)
    assert os.path.getsize(saved_empty) == 0


@patch('requests.post')
def test_adversarial_upload_corrupted_binary_bytes(mock_post, client, base_ia_success_response):
    """Uploading non-video random garbage binary with .mp4 extension forwards cleanly without crashing."""
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    garbage_bytes = b"\xff\xfe\x00\x01\xde\xad\xbe\xef" * 128
    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (io.BytesIO(garbage_bytes), 'corrupted.mp4'),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    forwarded_bytes = mock_post.call_args[1]['files']['file'][1]
    assert forwarded_bytes == garbage_bytes


@pytest.mark.parametrize("hostile_filename", [
    "video.mp4.exe",
    "video.mp4.sh",
    "exploit.mp4.php",
    "payload.mp4.html",
    "script.mp4.js",
    "archive.mp4.tar.gz",
    "no_extension",
    ".",
    "..",
])
def test_adversarial_upload_disallowed_extensions_rejected(client, hostile_filename):
    """Files with disallowed trailing extensions or no extensions must be rejected with HTTP 400."""
    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (io.BytesIO(b"testcontent"), hostile_filename),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    data = res.get_json()
    assert 'error' in data
    assert 'Formato no permitido' in data['error'] or 'No se seleccion\u00f3 ning\u00fan archivo' in data['error']


@pytest.mark.parametrize("valid_extension_filename", [
    "pullup_test.MP4",
    "pullup_test.MOV",
    "pullup_test.AVI",
    "pullup_test.WEBM",
    "pullup_test.Mp4",
    "pullup_test.MoV",
    "pullup_test.WebM",
    "complex.name.with.dots.mp4",
])
@patch('requests.post')
def test_adversarial_upload_case_insensitive_valid_extensions(mock_post, client, base_ia_success_response, valid_extension_filename):
    """Uppercase and mixed-case extensions for allowed formats (.mp4, .mov, .avi, .webm) must be accepted."""
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (io.BytesIO(b"dummy_video_bytes"), valid_extension_filename),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 200


@patch('requests.post')
def test_adversarial_upload_path_traversal_filename_sanitized(mock_post, client, base_ia_success_response):
    """Filenames with directory traversal characters (../../etc/passwd.mp4) must be sanitized within UPLOAD_FOLDER."""
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(base_ia_success_response).encode('utf-8')
    )

    traversal_name = "../../../../etc/passwd.mp4"
    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (io.BytesIO(b"traversal_test"), traversal_name),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 200

    # Ensure no file was written outside UPLOAD_FOLDER
    upload_dir = app.config['UPLOAD_FOLDER']
    written_files = os.listdir(upload_dir)
    for fname in written_files:
        full_path = os.path.join(upload_dir, fname)
        assert os.path.commonpath([upload_dir, full_path]) == upload_dir
        assert "etc" in fname
        assert "passwd.mp4" in fname


def test_adversarial_upload_max_content_length_limit(client):
    """Uploading a file exceeding MAX_CONTENT_LENGTH triggers RequestEntityTooLarge error."""
    original_limit = app.config.get('MAX_CONTENT_LENGTH')
    app.config['MAX_CONTENT_LENGTH'] = 100
    try:
        res = client.post(
            '/ejercicio2/app2-front/upload',
            data={'file': (io.BytesIO(b"X" * 200), "oversized.mp4")},
            content_type='multipart/form-data'
        )
        assert res.status_code in (413, 500)
        data = res.get_json()
        assert 'error' in data
        assert '413' in data['error'] or 'Request Entity Too Large' in data['error']
    finally:
        app.config['MAX_CONTENT_LENGTH'] = original_limit


# ============================================================================
# 3. MOCK TRUEREP-IA EDGE RESPONSES & UPSTREAM OUTAGES
# ============================================================================

@pytest.mark.parametrize("upstream_status", [500, 502, 503, 504, 400, 422])
@patch('requests.post')
def test_adversarial_upstream_http_status_errors(mock_post, client, sample_video, upstream_status):
    """When TrueRep-IA responds with non-200 code, proxy returns HTTP 502 Bad Gateway with code."""
    stream, filename = sample_video
    mock_post.return_value = MagicMock(
        status_code=upstream_status,
        content=f"Error {upstream_status}".encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 502
    data = res.get_json()
    assert 'error' in data
    assert f"c\u00f3digo {upstream_status}" in data['error']


@pytest.mark.parametrize("exception_class,msg", [
    (requests.exceptions.ConnectTimeout, "Connection timed out after 5s"),
    (requests.exceptions.ReadTimeout, "Read timed out after 600s"),
    (requests.exceptions.ConnectionError, "Failed to establish a new connection: [Errno 111] Connection refused"),
    (requests.exceptions.ChunkedEncodingError, "Response ended prematurely"),
])
@patch('requests.post')
def test_adversarial_upstream_network_exceptions(mock_post, client, sample_video, exception_class, msg):
    """Network connection exceptions during upstream calls are caught and return HTTP 500."""
    stream, filename = sample_video
    mock_post.side_effect = exception_class(msg)

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 500
    data = res.get_json()
    assert 'error' in data
    assert "Error:" in data['error']


@pytest.mark.parametrize("malformed_body", [
    b"<html><head><title>502 Bad Gateway</title></head><body><h1>Bad Gateway</h1></body></html>",
    b"{'invalid_json': true}",                          # Single quotes
    b'{"ejercicio": "pullup", "repeticiones": [',       # Truncated JSON
    b"\x00\x01\x02\x03",                               # Raw binary
    b"",                                                # Empty body
])
@patch('requests.post')
def test_adversarial_upstream_malformed_json_response(mock_post, client, sample_video, malformed_body):
    """When upstream returns 200 with non-JSON or malformed payload, JSONDecodeError is caught -> 500."""
    stream, filename = sample_video
    mock_post.return_value = MagicMock(
        status_code=200,
        content=malformed_body
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 500
    data = res.get_json()
    assert 'error' in data


@patch('requests.post')
def test_adversarial_upstream_empty_repeticiones_list(mock_post, client, sample_video):
    """When TrueRep-IA detects zero repetitions, response contract is cleanly preserved."""
    stream, filename = sample_video
    zero_rep_response = {
        "ejercicio": "pullup",
        "ejercicio_nombre": "Dominadas (Pull-up)",
        "nivel": "standard",
        "nivel_nombre": "Est\u00e1ndar Deportivo",
        "repeticiones_validas": 0,
        "intentos_totales": 0,
        "repeticiones_invalidas": 0,
        "duracion_video": 10.0,
        "tiempo_procesamiento": 3.2,
        "diagnostico_general": "No se detectaron repeticiones de dominadas en el video.",
        "repeticiones": [],
        "video_procesado": None
    }
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(zero_rep_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data['repeticiones_validas'] == 0
    assert data['intentos_totales'] == 0
    assert data['repeticiones'] == []
    assert 'video_url' not in data


@patch('requests.post')
def test_adversarial_upstream_missing_metric_fields_in_reps(mock_post, client, sample_video):
    """When upstream omits repetition fields, TrueRep-Front forwards payload without crashing."""
    stream, filename = sample_video
    sparse_response = {
        "ejercicio": "pullup",
        "repeticiones_validas": 1,
        "intentos_totales": 1,
        "repeticiones_invalidas": 0,
        "repeticiones": [
            {
                "numero": 1,
                "valida": True
                # angulo_inflexion, angulo_extension, angulo_postura, timestamps, fallos omitted
            }
        ]
    }
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(sparse_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    data = res.get_json()
    assert len(data['repeticiones']) == 1
    assert data['repeticiones'][0]['valida'] is True


@patch('requests.post')
def test_adversarial_upstream_extreme_metric_values(mock_post, client, sample_video):
    """When upstream returns extreme angle or timestamp values (-999° or 999°), payload forwards cleanly."""
    stream, filename = sample_video
    extreme_response = {
        "ejercicio": "pullup",
        "repeticiones_validas": 0,
        "intentos_totales": 1,
        "repeticiones_invalidas": 1,
        "repeticiones": [
            {
                "numero": 1,
                "valida": False,
                "motivo": "Valores extremos de prueba",
                "fallos": ["Inflexi\u00f3n fuera de rango f\u00edsico"],
                "start_time": -100.0,
                "end_time": 999999.0,
                "timestamp": 500000.0,
                "angulo_inflexion": -999.0,
                "angulo_extension": 999.0,
                "angulo_postura": 180.0
            }
        ]
    }
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(extreme_response).encode('utf-8')
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    data = res.get_json()
    rep = data['repeticiones'][0]
    assert rep['angulo_inflexion'] == -999.0
    assert rep['angulo_extension'] == 999.0


@patch('requests.get')
@patch('requests.post')
def test_adversarial_upstream_video_download_failure_resilience(mock_post, mock_get, client, sample_video, base_ia_success_response):
    """If downloading video_procesado from IA fails (HTTP 404 or 500), proxy returns JSON without crashing."""
    stream, filename = sample_video
    resp_with_video = dict(base_ia_success_response)
    resp_with_video["video_procesado"] = "processed_pullup_test.mp4"
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(resp_with_video).encode('utf-8')
    )
    # Simulate 404 Not Found on video endpoint
    mock_get.return_value = MagicMock(status_code=404)

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data['ejercicio'] == 'pullup'
    # video_url should not be present since video download failed
    assert 'video_url' not in data


@patch('requests.get')
@patch('requests.post')
def test_adversarial_upstream_video_download_timeout_handled(mock_post, mock_get, client, sample_video, base_ia_success_response):
    """If downloading video_procesado times out, exception is caught returning HTTP 500."""
    stream, filename = sample_video
    resp_with_video = dict(base_ia_success_response)
    resp_with_video["video_procesado"] = "processed_pullup_test.mp4"
    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(resp_with_video).encode('utf-8')
    )
    mock_get.side_effect = requests.exceptions.ReadTimeout("Video download timed out")

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 500
    data = res.get_json()
    assert 'error' in data
    assert "Video download timed out" in data['error']


# ============================================================================
# 4. JINJA2 TEMPLATE STRESS-TESTING & DOM INTEGRITY
# ============================================================================

def test_adversarial_jinja2_template_renders_with_unexpected_kwargs(client):
    """index.html must render cleanly when passed unexpected, large, or hostile context variables."""
    from flask import render_template

    with app.test_request_context():
        rendered = render_template(
            'index.html',
            unexpected_script="<script>alert('pwn')</script>",
            huge_param="X" * 100000,
            none_param=None,
            list_param=[1, 2, 3],
            dict_param={"key": "val"}
        )

        assert 'Dominadas (Pull-up)' in rendered
        assert 'id="chips-pullup"' in rendered
        assert 'data-exercise="pullup"' in rendered
        # Verify hostile variable was not blindly injected unescaped
        assert "<script>alert('pwn')</script>" not in rendered


def test_adversarial_jinja2_dom_elements_present_for_milestone_3(client):
    """Verifies all required DOM nodes, IDs, and attributes exist for pullup workflow."""
    res = client.get('/ejercicio2/app2-front/')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    required_ids = [
        'view-1', 'view-2', 'view-3',
        'exercise-label', 'dropzone-sub',
        'chips-pullup', 'chips-squat', 'chips-pushup',
        'start-btn', 'video-input',
        'progress-fill', 'progress-msg',
        'result-video', 'timeline-track', 'timeline-progress',
        'timeline-segments', 'timeline-markers', 'timeline-playhead',
        'rep-list'
    ]
    for dom_id in required_ids:
        assert f'id="{dom_id}"' in html, f"Required DOM id='{dom_id}' missing in index.html"

    # Verify pull-up data-exercise attribute
    assert 'data-exercise="pullup"' in html
    # Verify standard metric chips inside #chips-pullup
    assert "Barbilla &gt; Barra" in html or "Barbilla > Barra" in html
    assert "Torso &le;30&deg;" in html or "Torso <= 30" in html
    assert "Extensi&oacute;n &ge;150&deg;" in html or "Extensión &ge;150" in html or "150" in html


# ============================================================================
# 5. CSS MEDIA QUERIES, SELECTORS & SYNTAX PARSING
# ============================================================================

def test_adversarial_css_syntax_and_balanced_delimiters():
    """Validates that TrueRep-Front/static/css/index.css has balanced delimiters and valid syntax."""
    css_path = os.path.join(FRONT_DIR, 'static', 'css', 'index.css')
    assert os.path.isfile(css_path), f"index.css not found at {css_path}"

    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip comments
    clean_chars = []
    in_comment = False
    i = 0
    while i < len(content):
        if not in_comment and content[i:i+2] == '/*':
            in_comment = True
            i += 2
        elif in_comment and content[i:i+2] == '*/':
            in_comment = False
            i += 2
        elif not in_comment:
            clean_chars.append(content[i])
            i += 1
        else:
            i += 1

    assert not in_comment, "Unclosed CSS comment found in index.css"

    # Balanced bracket/brace check
    clean_css = ''.join(clean_chars)
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    for idx, ch in enumerate(clean_css):
        if ch in '({[':
            stack.append((ch, idx))
        elif ch in ')}]':
            assert stack, f"Unmatched closing delimiter '{ch}' at offset {idx}"
            top, _ = stack.pop()
            assert top == pairs[ch], f"Mismatched delimiters: '{top}' and '{ch}' at offset {idx}"

    assert len(stack) == 0, f"Unclosed delimiters remaining: {len(stack)}"


def test_adversarial_css_media_queries_integrity():
    """Verifies that all @media blocks parse cleanly and target correct responsive breakpoints."""
    css_path = os.path.join(FRONT_DIR, 'static', 'css', 'index.css')
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all media query headers
    media_headers = re.findall(r'@media\s*([^{]+)\{', content)
    assert len(media_headers) >= 4, f"Expected at least 4 @media queries, found {len(media_headers)}"

    normalized_headers = [h.strip() for h in media_headers]

    # Verify standard responsive & accessibility breakpoints
    assert any("max-width: 768px" in h for h in normalized_headers), "Tablet breakpoint (768px) missing"
    assert any("max-width: 480px" in h for h in normalized_headers), "Mobile breakpoint (480px) missing"
    assert any("hover: hover" in h and "pointer: fine" in h for h in normalized_headers), "Fine pointer query missing"
    assert any("prefers-reduced-motion: reduce" in h for h in normalized_headers), "Reduced motion query missing"


def test_adversarial_css_no_broken_selectors():
    """Verifies there are no stray commas or empty selectors in index.css."""
    css_path = os.path.join(FRONT_DIR, 'static', 'css', 'index.css')
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content_no_comments = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    rule_pattern = re.compile(r'([^{}@]+)\{([^{}]+)\}', re.MULTILINE)
    matches = rule_pattern.findall(content_no_comments)

    assert len(matches) > 50, "CSS rules count unexpectedly low"

    for sel_group, _ in matches:
        sel_group = sel_group.strip()
        assert sel_group, "Empty selector group found"
        assert not sel_group.endswith(','), f"Trailing comma before open brace in selector: {sel_group!r}"
        assert not sel_group.startswith(','), f"Leading comma in selector: {sel_group!r}"


def test_adversarial_css_responsive_3_column_grid_definitions():
    """Verifies that 3-column exercise grid and 2-column level grid are correctly scoped."""
    css_path = os.path.join(FRONT_DIR, 'static', 'css', 'index.css')
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Exercise selector must define repeat(3, 1fr) for exercise-grid or :has([data-exercise])
    assert re.search(r'\.exercise-selector\.exercise-grid[^}]*repeat\(3,\s*1fr\)', content, re.DOTALL) or \
           re.search(r'\.exercise-selector:has\(\[data-exercise\]\)[^}]*repeat\(3,\s*1fr\)', content, re.DOTALL), \
           "3-column definition missing for exercise-grid"

    # Level selector must specify 1fr 1fr
    assert re.search(r'\.exercise-selector\.level-grid[^}]*1fr\s+1fr', content, re.DOTALL) or \
           re.search(r'\.exercise-selector:has\(\[data-level\]\)[^}]*1fr\s+1fr', content, re.DOTALL), \
           "2-column definition missing for level-grid"


# ============================================================================
# 6. AUXILIARY ENDPOINTS & UTILITY ROBUSTNESS
# ============================================================================

@pytest.mark.parametrize("status_failure", [
    MagicMock(status_code=500),
    MagicMock(status_code=503),
    MagicMock(status_code=200, json=lambda: (_ for _ in ()).throw(ValueError("malformed"))),
])
@patch('requests.get')
def test_adversarial_status_endpoint_fallback(mock_get, client, status_failure):
    """GET /status returns default fallback state on any upstream status error."""
    mock_get.return_value = status_failure

    res = client.get('/ejercicio2/app2-front/status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['stage'] == 'pose'
    assert data['percent'] == 10
    assert 'Procesando video' in data['message']


def test_adversarial_display_route_directory_traversal_rejection(client):
    """GET /display/<traversal> must be rejected with 404 by Flask's url routing."""
    res = client.get('/ejercicio2/app2-front/display/..%2F..%2Fetc%2Fpasswd')
    assert res.status_code == 404


def test_adversarial_cleanup_old_files_boundary_conditions(tmp_path):
    """cleanup_old_files handles nonexistent directories, hidden files, subdirs, and max_files=0."""
    # 1. Nonexistent directory
    nonexistent = tmp_path / "nonexistent_dir"
    cleanup_old_files(str(nonexistent), max_files=5)  # Must not raise

    # 2. Directory with subdirectories and hidden files
    test_dir = tmp_path / "complex_cleanup"
    test_dir.mkdir()
    (test_dir / "subdir").mkdir()
    (test_dir / ".hidden_file").write_text("hidden")
    (test_dir / "keep.mp4").write_text("keep")

    cleanup_old_files(str(test_dir), max_files=1)
    # Subdir and hidden file should not be pruned or crash the cleaner
    assert (test_dir / "subdir").is_dir()
    assert (test_dir / ".hidden_file").is_file()
    assert (test_dir / "keep.mp4").is_file()

    # 3. max_files=0 prunes all regular files
    cleanup_old_files(str(test_dir), max_files=0)
    assert not (test_dir / "keep.mp4").exists()
    assert (test_dir / "subdir").is_dir()
    assert (test_dir / ".hidden_file").is_file()
