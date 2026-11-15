
"""NAO physical robot session coordinator for reemwork/NAO-Emotion-Recognition.

Run from repository root: python run_session.py --nao-ip 169.254.x.x
Requires NAO Python 2 + NAOqi available on the robot via SSH and working
PC FastAPI/Whisper/Ollama. Does not fabricate CV classification results.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
API = "http://127.0.0.1:8000"
OLLAMA = "http://127.0.0.1:11434"
MODEL = "qwen2.5vl:3b"

# NAO V6 stores its Python 2 NAOqi bindings outside Python's default path.
NAO_PYTHON_COMMAND = (
    'env PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:'
    '/opt/aldebaran/lib python -'
)


class IntegrationError(RuntimeError):
    pass


def req(method, path, **kwargs):
    try:
        res = requests.request(
            method, API + path, timeout=kwargs.pop('timeout', 30), **kwargs
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as error:
        detail = getattr(getattr(error, 'response', None), 'text', '')
        raise IntegrationError(
            '%s %s: %s %s' % (method, path, error, detail[:400])
        ) from error


def robot_ssh_command(ip):
    return [
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
        'nao@' + ip, NAO_PYTHON_COMMAND,
    ]


def probe_robot(ip):
    # Send Python 2 code through stdin: avoids nested PowerShell/SSH quoting.
    p = subprocess.run(
        robot_ssh_command(ip),
        input='import naoqi\nprint("NAOQI_OK")\n',
        capture_output=True,
        text=True,
        timeout=16,
    )
    if p.returncode or 'NAOQI_OK' not in p.stdout:
        raise IntegrationError(
            'Robot SSH/NAOqi check failed: '
            + (p.stderr or p.stdout or 'No output from robot').strip()[-500:]
        )


def preflight(ip, check_robot=True):
    req('GET', '/')
    try:
        r = requests.get(OLLAMA + '/api/tags', timeout=10)
        r.raise_for_status()
        names = [x.get('name', '') for x in r.json().get('models', [])]
        if MODEL not in names:
            raise IntegrationError(
                'Ollama model %s missing. Installed models: %s' % (MODEL, names)
            )
    except requests.RequestException as e:
        raise IntegrationError('Ollama unreachable at %s: %s' % (OLLAMA, e)) from e
    if check_robot:
        probe_robot(ip)


# This runs under Python 2 on NAO. Never use Python 3-only syntax in it.
ROBOT_SCRIPT = r'''
from naoqi import ALProxy
import base64, os, time, sys
ip = "127.0.0.1"
tts = ALProxy("ALTextToSpeech", ip, 9559)
recorder = ALProxy("ALAudioRecorder", ip, 9559)
photo = ALProxy("ALPhotoCapture", ip, 9559)
question = base64.b64decode("__QUESTION_B64__")
label = "__LABEL__"
audio = "/home/nao/" + label + ".wav"
image = "/home/nao/" + label + ".jpg"
try:
    if os.path.exists(audio): os.unlink(audio)
    if os.path.exists(image): os.unlink(image)
    tts.say(question)
    recorder.startMicrophonesRecording(audio, "wav", 16000, (0, 0, 1, 0))
    try:
        time.sleep(2)
        photo.setCameraID(0)
        photo.setResolution(2)
        photo.setPictureFormat("jpg")
        returned = photo.takePicture("/home/nao", label)
        # Some NAOqi versions return paths; others use the requested path.
        if not os.path.isfile(image):
            candidates = returned if isinstance(returned, (list, tuple)) else [returned]
            for candidate in candidates:
                if isinstance(candidate, basestring) and os.path.isfile(candidate):
                    image = candidate
                    break
        time.sleep(6)
    finally:
        recorder.stopMicrophonesRecording()
    if not os.path.isfile(audio): raise RuntimeError("Audio not created")
    if not os.path.isfile(image): raise RuntimeError("Camera image not created: " + str(returned))
    print("__AUDIO__=" + audio)
    print("__IMAGE__=" + image)
except Exception as e:
    sys.stderr.write("CAPTURE_ERROR: " + str(e) + "\n")
    sys.exit(2)
'''


def capture_from_robot(ip, question, label, dest):
    safe_label = re.sub(r'[^A-Za-z0-9_]', '_', label)
    src = (
        ROBOT_SCRIPT
        .replace('__QUESTION_B64__', base64.b64encode(question.encode('utf-8')).decode('ascii'))
        .replace('__LABEL__', safe_label)
    )
    p = subprocess.run(
        robot_ssh_command(ip),
        input=src,
        capture_output=True,
        text=True,
        timeout=100,
    )
    if p.returncode:
        raise IntegrationError('NAO capture failed: ' + (p.stderr or p.stdout)[-900:])

    outputs = dict(
        x.split('=', 1) for x in p.stdout.splitlines()
        if x.startswith(('__AUDIO__=', '__IMAGE__='))
    )
    if '__AUDIO__' not in outputs or '__IMAGE__' not in outputs:
        raise IntegrationError('Missing capture paths from NAO: ' + p.stdout[-700:])

    local_audio = dest / (safe_label + '.wav')
    local_image = dest / (safe_label + '.jpg')
    for remote, local in (
        (outputs['__AUDIO__'], local_audio),
        (outputs['__IMAGE__'], local_image),
    ):
        if not remote.startswith('/home/nao/'):
            raise IntegrationError('Unsafe remote capture path: ' + remote)
        subprocess.run(
            ['scp', '-o', 'BatchMode=yes', 'nao@' + ip + ':' + remote, str(local)],
            check=True,
            timeout=90,
        )
        if not local.is_file() or not local.stat().st_size:
            raise IntegrationError('Empty capture: ' + str(local))
    return local_audio, local_image


def upload_capture(sid, scenario_id, audio, image):
    with image.open('rb') as f:
        req(
            'POST', '/api/camera/session-frame',
            data={'session_id': sid, 'scenario_id': str(scenario_id)},
            files={'frame': (image.name, f, 'image/jpeg')},
            timeout=60,
        )
    with audio.open('rb') as f:
        return req(
            'POST', '/api/audio/evaluate',
            data={'session_id': sid, 'scenario_id': str(scenario_id)},
            files={'audio': (audio.name, f, 'audio/wav')},
            timeout=360,
        )


def show_image(scenario):
    rel = scenario.get('image_path', '')
    path = (ROOT / rel).resolve()
    if ROOT not in path.parents or not path.is_file():
        print('WARNING: scenario image missing:', rel)
        return
    webbrowser.open(path.as_uri())


def run(args):
    print('Checking backend, local MLLM and robot...')
    preflight(args.nao_ip, not args.samples_dir)
    print('Preflight OK.')
    sid = req('POST', '/api/session/start')['session_id']
    print('Session:', sid)
    try:
        with tempfile.TemporaryDirectory(prefix='nao_session_') as tmp:
            folder = Path(tmp)
            index = 0
            while True:
                response = req('GET', '/api/scenario/next', params={'index': index})
                if not response.get('has_more'):
                    break
                scenario = response['scenario']
                scenario_id = int(scenario['scenario_id'])
                print('\nScenario %s - reference label: %s' % (
                    scenario_id, scenario['reference_label']
                ))
                req('POST', '/api/scenario/start', json={
                    'session_id': sid, 'scenario_id': scenario_id,
                })
                show_image(scenario)
                question = args.question
                try:
                    if args.samples_dir:
                        audio = args.samples_dir / ('scenario_%s.wav' % scenario_id)
                        image = args.samples_dir / ('scenario_%s.jpg' % scenario_id)
                        if not (audio.is_file() and image.is_file()):
                            raise IntegrationError(
                                'Sample WAV/JPG not found for scenario %s' % scenario_id
                            )
                    else:
                        audio, image = capture_from_robot(
                            args.nao_ip, question,
                            'nao_%s_%s' % (sid[:8], scenario_id), folder,
                        )
                    result = upload_capture(sid, scenario_id, audio, image)
                    print('Evaluated:', json.dumps(result, ensure_ascii=False)[:900])
                    req('POST', '/api/scenario/complete', json={
                        'session_id': sid, 'scenario_id': scenario_id,
                    })
                except (IntegrationError, subprocess.CalledProcessError,
                        subprocess.TimeoutExpired) as e:
                    print('WARNING: scenario %s failed: %s' % (scenario_id, e))
                    reason = 'processing_failed'
                    if 'Sample WAV/JPG not found' in str(e):
                        reason = 'no_response'
                    req('POST', '/api/scenario/recovery', json={
                        'session_id': sid, 'scenario_id': scenario_id,
                        'action': 'skip', 'reason': reason,
                    })
                index += 1
    finally:
        # Preserve active-scenario state for inspection if unexpected errors occur.
        try:
            session = req('GET', '/api/session/' + sid)
            active = session.get('active_scenario_id')
            if active is not None:
                req('POST', '/api/scenario/recovery', json={
                    'session_id': sid, 'scenario_id': active,
                    'action': 'skip', 'reason': 'processing_failed',
                })
            req('POST', '/api/session/end', json={'session_id': sid})
            report = req('GET', '/api/session/' + sid + '/report')
            output = ROOT / 'data' / ('session_%s_report.json' % sid)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8'
            )
            print('\nReport saved:', output)
            print('HTML report:', API + '/api/session/' + sid + '/report/view')
        except Exception as e:
            print('WARNING: could not finalize session: %s' % e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run NAO scenarios via existing FastAPI backend'
    )
    parser.add_argument(
        '--nao-ip', default=os.environ.get('NAO_IP', '169.254.247.199')
    )
    parser.add_argument(
        '--question', default='What emotion do you see in this picture?'
    )
    parser.add_argument(
        '--samples-dir', type=Path,
        help='Replay scenario_1.wav/jpg etc. without NAO (real AI required)',
    )
    args = parser.parse_args()
    try:
        run(args)
    except (IntegrationError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as e:
        print('ERROR:', e, file=sys.stderr)
        sys.exit(1)
