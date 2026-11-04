# -*- coding: utf-8 -*-
"""
Automated Pytest Test Suite for TrueRep-Front Pull-Up Integration (Milestone 3).
Target Path: TrueRep-Front/tests/test_front_pullup.py

Coverage:
1. Template Rendering (GET /ejercicio2/app2-front/ & GET /):
   - Button 'Dominadas (Pull-up)' with data-exercise="pullup"
   - Container '#chips-pullup' and standard metric chips (Barbilla > Barra, Torso <= 30°, Extensión >= 150°)
   - Root redirect to /ejercicio2/app2-front/
2. Upload Request Validation (POST /ejercicio2/app2-front/upload):
   - Missing 'file' key rejection (HTTP 400)
   - Empty filename rejection (HTTP 400)
   - Disallowed extension rejection (HTTP 400)
   - Allowed extension acceptance (.mp4, .mov, .avi, .webm)
   - Defensive validation: 'pullup', 'squat', 'pushup' allowed; invalid/missing defaults safely to 'squat'
   - Level validation: 'standard', 'strict' allowed; invalid/missing defaults safely to 'standard'
3. TrueRep-IA Proxy & Forwarding:
   - Forwarding headers (X-API-KEY), form fields (exercise=pullup, level), and multipart file
   - Successful proxying of pullup analysis results and processed video download
   - Upstream 500/502 error forwarding
   - Upstream network connection/timeout exception handling
4. Auxiliary Proxy Endpoints:
   - Status polling proxy (GET /ejercicio2/app2-front/status) with upstream fallback
   - Display video redirect (GET /ejercicio2/app2-front/display/<filename>)
"""

import io
import os
import sys
import json
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
from main import API_KEY_HEADER
from utils import allowed_file, cleanup_old_files


@pytest.fixture
def client(tmp_path):
    """Configures Flask test client with an isolated temporary uploads directory."""
    test_upload_folder = str(tmp_path / "uploads")
    os.makedirs(test_upload_folder, exist_ok=True)

    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = test_upload_folder

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def dummy_video():
    """Returns a dummy video byte stream and filename for upload testing."""
    content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free"
    return io.BytesIO(content), "pullup_test.mp4"


@pytest.fixture
def mock_ia_pullup_response():
    """Returns a sample valid JSON response from TrueRep-IA for pullup analysis."""
    return {
        "ejercicio": "pullup",
        "ejercicio_nombre": "Dominadas (Pull-up)",
        "nivel": "standard",
        "nivel_nombre": "Estándar Deportivo",
        "repeticiones_validas": 5,
        "intentos_totales": 6,
        "repeticiones_invalidas": 1,
        "duracion_video": 24.5,
        "tiempo_procesamiento": 8.2,
        "diagnostico_general": "Buen desempeño general. Se detectaron 5 repeticiones válidas y 1 con extensión incompleta.",
        "repeticiones": [
            {
                "numero": 1,
                "valida": True,
                "motivo": "Repetición válida",
                "fallos": [],
                "start_time": 1.5,
                "end_time": 4.2,
                "timestamp": 2.8,
                "angulo_inflexion": 48.0,
                "angulo_extension": 165.0,
                "angulo_postura": 12.0
            },
            {
                "numero": 2,
                "valida": False,
                "motivo": "Extensión de codos incompleta al bajar (codo 135.0° < 150°)",
                "fallos": ["Extensión de codos incompleta al bajar (codo 135.0° < 150°)"],
                "start_time": 4.8,
                "end_time": 7.5,
                "timestamp": 6.1,
                "angulo_inflexion": 52.0,
                "angulo_extension": 135.0,
                "angulo_postura": 15.0
            }
        ],
        "video_procesado": "pullup_123_skeleton.mp4"
    }


# ============================================================================
# 1. TEMPLATE & ROUTE RENDERING TESTS
# ============================================================================

def test_root_redirect(client):
    """GET / should redirect to /ejercicio2/app2-front/ with 302."""
    res = client.get('/')
    assert res.status_code == 302
    assert '/ejercicio2/app2-front/' in res.headers['Location']


def test_index_form_render_status(client):
    """GET /ejercicio2/app2-front/ returns HTTP 200 OK."""
    res = client.get('/ejercicio2/app2-front/')
    assert res.status_code == 200
    assert 'text/html' in res.content_type


def test_index_contains_pullup_exercise_card(client):
    """Verifies that Dominadas (Pull-up) option card exists with proper data attribute."""
    res = client.get('/ejercicio2/app2-front/')
    html = res.get_data(as_text=True)

    assert 'data-exercise="pullup"' in html, "Card with data-exercise='pullup' missing in index.html"
    assert "Dominadas (Pull-up)" in html, "Title 'Dominadas (Pull-up)' missing in index.html"
    assert "selectExercise('pullup')" in html or 'selectExercise("pullup")' in html


def test_index_contains_chips_pullup_container(client):
    """Verifies that container #chips-pullup is present for dynamic chip updates."""
    res = client.get('/ejercicio2/app2-front/')
    html = res.get_data(as_text=True)

    assert 'id="chips-pullup"' in html, "Container id='chips-pullup' missing in index.html"


def test_index_pullup_chips_standard_thresholds(client):
    """Verifies standard metric chips rendered inside #chips-pullup."""
    res = client.get('/ejercicio2/app2-front/')
    html = res.get_data(as_text=True)

    # Check Chin clearance chip
    assert ("Barbilla > Barra" in html or "Barbilla &gt; Barra" in html), \
        "Standard chin chip 'Barbilla > Barra' missing in index.html"

    # Check Torso inclination / kipping limit chip
    assert ("Torso" in html and "30" in html), \
        "Standard torso chip 'Torso <= 30°' missing in index.html"

    # Check Extension lockout chip
    assert ("Extensión" in html or "Extensi&oacute;n" in html) and "150" in html, \
        "Standard extension chip 'Extensión >= 150°' missing in index.html"


def test_index_retains_squat_and_pushup_options(client):
    """Verifies backward compatibility: Sentadilla and Flexiones remain present."""
    res = client.get('/ejercicio2/app2-front/')
    html = res.get_data(as_text=True)

    assert 'data-exercise="squat"' in html
    assert 'data-exercise="pushup"' in html
    assert 'id="chips-squat"' in html
    assert 'id="chips-pushup"' in html


def test_index_contains_level_selector_buttons(client):
    """Verifies standard and strict level buttons are present."""
    res = client.get('/ejercicio2/app2-front/')
    html = res.get_data(as_text=True)

    assert 'data-level="standard"' in html
    assert 'data-level="strict"' in html


# ============================================================================
# 2. UPLOAD REQUEST VALIDATION & DEFENSIVE PARAMS
# ============================================================================

def test_upload_missing_file_key(client):
    """POST /upload without 'file' field must return 400 Bad Request."""
    res = client.post('/ejercicio2/app2-front/upload', data={'exercise': 'pullup'})
    assert res.status_code == 400
    data = res.get_json()
    assert 'error' in data
    assert 'No se envió ningún archivo de video' in data['error']


def test_upload_empty_filename(client):
    """POST /upload with empty filename must return 400."""
    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (io.BytesIO(b'dummy'), ''),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    data = res.get_json()
    assert 'error' in data
    assert 'No se seleccionó ningún archivo' in data['error']


def test_upload_disallowed_extension(client):
    """POST /upload with disallowed file extension (.txt) must return 400."""
    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (io.BytesIO(b'plain text'), 'video.txt'),
            'exercise': 'pullup'
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    data = res.get_json()
    assert 'error' in data
    assert 'Formato no permitido' in data['error']


@pytest.mark.parametrize("filename,expected", [
    ("pullup.mp4", True),
    ("pullup.MOV", True),
    ("pullup.avi", True),
    ("pullup.WEBM", True),
    ("pullup.exe", False),
    ("pullup.png", False),
    ("pullup.mp3", False),
    ("document.doc", False),
    ("noextension", False),
])
def test_allowed_file_extensions(filename, expected):
    """Tests the allowed_file helper against valid and invalid extensions."""
    assert allowed_file(filename) is expected


def test_allowed_exercises_and_levels_constants():
    """Validates defensive whitelist constants in main.py."""
    assert hasattr(main, 'ALLOWED_EXERCISES'), "main.py missing ALLOWED_EXERCISES constant"
    assert hasattr(main, 'ALLOWED_LEVELS'), "main.py missing ALLOWED_LEVELS constant"
    assert 'pullup' in main.ALLOWED_EXERCISES
    assert 'squat' in main.ALLOWED_EXERCISES
    assert 'pushup' in main.ALLOWED_EXERCISES
    assert 'standard' in main.ALLOWED_LEVELS
    assert 'strict' in main.ALLOWED_LEVELS


# ============================================================================
# 3. DEFENSIVE PARAMETER FALLBACK & MULTIPART FORWARDING
# ============================================================================

@patch('requests.get')
@patch('requests.post')
def test_upload_pullup_forwarding_parameters(mock_post, mock_get, client, dummy_video, mock_ia_pullup_response):
    """Verifies that exercise='pullup' and level='standard' are properly forwarded to TrueRep-IA."""
    stream, filename = dummy_video

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = json.dumps(mock_ia_pullup_response).encode('utf-8')
    mock_post.return_value = mock_resp

    mock_vid_resp = MagicMock()
    mock_vid_resp.status_code = 200
    mock_vid_resp.content = b'annotated_video_binary'
    mock_get.return_value = mock_vid_resp

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (stream, filename, 'video/mp4'),
            'exercise': 'pullup',
            'level': 'standard'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    assert mock_post.called

    # Validate target URL and headers
    call_args, call_kwargs = mock_post.call_args
    assert call_args[0] == IA_SERVER + IA_URL
    assert call_kwargs['headers'] == API_KEY_HEADER
    assert call_kwargs['timeout'] == (5, 600)

    # Validate forwarded payload
    forwarded_data = call_kwargs['data']
    assert forwarded_data['exercise'] == 'pullup'
    assert forwarded_data['level'] == 'standard'

    # Validate forwarded files
    forwarded_files = call_kwargs['files']
    assert 'file' in forwarded_files
    assert forwarded_files['file'][2] == 'video/mp4'


@patch('requests.get')
@patch('requests.post')
def test_upload_defensive_exercise_fallback(mock_post, mock_get, client, dummy_video, mock_ia_pullup_response):
    """Verifies invalid or unknown exercise defaults safely to 'squat'."""
    stream, filename = dummy_video

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = json.dumps(mock_ia_pullup_response).encode('utf-8')
    mock_post.return_value = mock_resp
    mock_get.return_value = MagicMock(status_code=404)

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (stream, filename, 'video/mp4'),
            'exercise': 'unsupported_aerobics',
            'level': 'unsupported_grade'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    forwarded_data = mock_post.call_args[1]['data']
    assert forwarded_data['exercise'] == 'squat'
    assert forwarded_data['level'] == 'standard'


@patch('requests.get')
@patch('requests.post')
def test_upload_pullup_strict_forwarding(mock_post, mock_get, client, dummy_video, mock_ia_pullup_response):
    """Verifies pullup with level='strict' forwards properly."""
    stream, filename = dummy_video

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = json.dumps(mock_ia_pullup_response).encode('utf-8')
    mock_post.return_value = mock_resp
    mock_get.return_value = MagicMock(status_code=404)

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={
            'file': (stream, filename, 'video/mp4'),
            'exercise': 'pullup',
            'level': 'strict'
        },
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    forwarded_data = mock_post.call_args[1]['data']
    assert forwarded_data['exercise'] == 'pullup'
    assert forwarded_data['level'] == 'strict'


# ============================================================================
# 4. RESPONSE PROXYING & PROCESSED VIDEO INGESTION
# ============================================================================

@patch('requests.get')
@patch('requests.post')
def test_upload_pullup_success_response_contract(mock_post, mock_get, client, dummy_video, mock_ia_pullup_response):
    """Verifies full response contract returned to frontend client."""
    stream, filename = dummy_video

    mock_post.return_value = MagicMock(
        status_code=200,
        content=json.dumps(mock_ia_pullup_response).encode('utf-8')
    )

    fake_video_bytes = b'FAKE_SKELETON_MP4_CONTENT'
    mock_get.return_value = MagicMock(
        status_code=200,
        content=fake_video_bytes
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 200
    data = res.get_json()

    assert data['ejercicio'] == 'pullup'
    assert data['repeticiones_validas'] == 5
    assert data['intentos_totales'] == 6
    assert data['repeticiones_invalidas'] == 1
    assert len(data['repeticiones']) == 2

    # Check repetition biomechanical metrics contract
    rep1 = data['repeticiones'][0]
    assert rep1['numero'] == 1
    assert rep1['valida'] is True
    assert 'angulo_inflexion' in rep1
    assert 'angulo_extension' in rep1
    assert 'angulo_postura' in rep1

    # Check that video_url was injected pointing to display route
    assert 'video_url' in data
    assert 'display/pullup_123_skeleton.mp4' in data['video_url']

    # Verify that local copy of annotated video was saved in upload folder
    saved_video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'pullup_123_skeleton.mp4')
    assert os.path.isfile(saved_video_path)
    with open(saved_video_path, 'rb') as vf:
        assert vf.read() == fake_video_bytes


# ============================================================================
# 5. ERROR HANDLING & UPSTREAM OUTAGES
# ============================================================================

@patch('requests.post')
def test_upload_ia_backend_500_error(mock_post, client, dummy_video):
    """When TrueRep-IA responds with non-200 code, proxy returns 502 Bad Gateway."""
    stream, filename = dummy_video

    mock_post.return_value = MagicMock(
        status_code=500,
        content=b'Internal Server Error'
    )

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 502
    data = res.get_json()
    assert 'error' in data
    assert 'Error contactando el módulo IA (código 500)' in data['error']


@patch('requests.post')
def test_upload_ia_backend_connection_exception(mock_post, client, dummy_video):
    """When requests.post raises an exception, proxy catches and returns 500."""
    stream, filename = dummy_video
    mock_post.side_effect = Exception("Connection refused to 127.0.0.1:7002")

    res = client.post(
        '/ejercicio2/app2-front/upload',
        data={'file': (stream, filename, 'video/mp4'), 'exercise': 'pullup'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 500
    data = res.get_json()
    assert 'error' in data
    assert 'Connection refused' in data['error']


# ============================================================================
# 6. AUXILIARY STATUS & DISPLAY ROUTES
# ============================================================================

@patch('requests.get')
def test_status_proxy_success(mock_get, client):
    """GET /status proxies upstream IA progress state successfully."""
    upstream_status = {
        'stage': 'rules',
        'percent': 75,
        'message': 'Evaluando reglas biomecánicas de dominadas...'
    }
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: upstream_status
    )

    res = client.get('/ejercicio2/app2-front/status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['stage'] == 'rules'
    assert data['percent'] == 75
    assert 'Evaluando reglas biomecánicas' in data['message']


@patch('requests.get')
def test_status_proxy_fallback_on_error(mock_get, client):
    """GET /status returns default fallback when IA status fails to respond."""
    mock_get.side_effect = Exception("Status timeout")

    res = client.get('/ejercicio2/app2-front/status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['stage'] == 'pose'
    assert data['percent'] == 10


def test_display_video_redirect(client):
    """GET /display/<filename> redirects with 301 to static/uploads/<filename>."""
    res = client.get('/ejercicio2/app2-front/display/test_output.mp4')
    assert res.status_code == 301
    assert '/ejercicio2/app2-front/static/uploads/test_output.mp4' in res.headers['Location']


def test_cleanup_old_files_utility(tmp_path):
    """Verifies that cleanup_old_files limits directory contents to max_files."""
    folder = tmp_path / "cleanup_test"
    folder.mkdir()

    # Create 5 files with distinct mtimes
    file_paths = []
    for i in range(5):
        fp = folder / f"file_{i}.mp4"
        fp.write_text(f"content {i}")
        # Adjust mtime
        os.utime(str(fp), (1000 + i * 10, 1000 + i * 10))
        file_paths.append(fp)

    assert len(os.listdir(str(folder))) == 5

    # Run cleanup with max_files=2
    cleanup_old_files(str(folder), max_files=2)

    remaining = sorted(os.listdir(str(folder)))
    assert len(remaining) == 2
    # Should keep the newest files (file_3 and file_4)
    assert remaining == ["file_3.mp4", "file_4.mp4"]
