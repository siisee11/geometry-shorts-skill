#!/usr/bin/env python3
"""The one entry point: needs only Python 3.10+. The first run makes a private environment with the packages the
scripts use (and an ffmpeg, via imageio-ffmpeg), then every run executes the script in it.

    python3 scripts/run.py <episode-dir> --plan              make.py: entries, values, camera, map area (fast)
    python3 scripts/run.py <episode-dir> --still 4.6,7.9     make.py: stills -> <episode-dir>/out/stills/
    python3 scripts/run.py <episode-dir> [--fps 30]          make.py: the video -> <episode-dir>/out/video.mp4
    python3 scripts/run.py countries 프랑스 japan             countries.py: Natural Earth code, flag code, area
    python3 scripts/run.py <script>.py ...                   any other script in this folder

The environment is <data>/venv (<data> = $MAP_SHORTS_DATA or ~/.cache/map-shorts) and is rebuilt when
requirements.txt changes. It is built with uv when uv is on PATH, else with `python -m venv` and pip.
"""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REQ = os.path.join(HERE, 'requirements.txt')
EXTRA = {}  # script -> packages it needs beyond requirements.txt
DATA = os.environ.get('MAP_SHORTS_DATA') or os.path.join(os.path.expanduser('~'), '.cache', 'map-shorts')
VENV = os.path.join(DATA, 'venv')
PY = os.path.join(VENV, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(VENV, 'bin', 'python')


def sh(cmd):
    print('+', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def ensure(extra=()):
    reqs = open(REQ).read().split() + list(extra)
    want = hashlib.sha1('\n'.join(reqs).encode()).hexdigest()
    mark = os.path.join(VENV, '.map-shorts-reqs')
    if os.path.exists(PY) and os.path.exists(mark) and open(mark).read() == want:
        return
    if sys.version_info < (3, 10):
        sys.exit(f'map-shorts needs Python 3.10 or newer (this is {sys.version.split()[0]})')
    print(f'setting up the map-shorts environment in {VENV} (once, about a minute)', flush=True)
    os.makedirs(DATA, exist_ok=True)
    uv = shutil.which('uv')
    if not os.path.exists(PY):
        if uv:
            sh([uv, 'venv', '--quiet', '--python', sys.executable, VENV])
        else:
            try:
                sh([sys.executable, '-m', 'venv', VENV])
            except subprocess.CalledProcessError:
                sys.exit('could not create a virtual environment: install uv (https://docs.astral.sh/uv/) '
                         'or the venv module (e.g. apt install python3-venv)')
    if uv:
        sh([uv, 'pip', 'install', '--quiet', '--python', PY] + reqs)
    else:
        sh([PY, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check'] + reqs)
    open(mark, 'w').write(want)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        sys.exit(__doc__)
    if args[0] == 'countries':
        script, rest = 'countries.py', args[1:]
    elif args[0].endswith('.py'):
        script, rest = os.path.basename(args[0]), args[1:]
    else:
        script, rest = 'make.py', args
    path = os.path.join(HERE, script)
    if not os.path.exists(path):
        sys.exit(f'no script {script} in {HERE}')
    ensure(EXTRA.get(script, ()))
    os.execv(PY, [PY, path] + rest)


if __name__ == '__main__':
    main()
