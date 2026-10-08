#!/usr/bin/env python3
"""Build a standalone executable on its target platform (Windows, Linux or macOS)."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-web-build', action='store_true',
                        help='Reuse existing web/static assets instead of running npm')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or later is required to build')
    windows = sys.platform == 'win32'
    environment = ROOT / '.local' / ('build-venv-windows' if windows else 'build-venv')
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if windows else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'requirements.txt',
                    'pyinstaller>=6.11,<7'], cwd=ROOT, check=True)
    if not args.skip_web_build:
        npm = shutil.which('npm.cmd' if windows else 'npm')
        if not npm:
            parser.error('Node.js and npm are required to build the webpage')
        for arguments in [('ci',), ('run', 'build')]:
            subprocess.run([npm, *arguments], cwd=ROOT, check=True)
    for asset in ['app.js', 'styles.css']:
        if not (ROOT / 'web/static' / asset).is_file():
            parser.error('Missing webpage assets; run without --skip-web-build')
    subprocess.run([str(python), '-m', 'PyInstaller', '--clean', '--noconfirm', 'work_hours.spec'],
                   cwd=ROOT, check=True)
    print('Executable: ' + str(ROOT / 'dist' / ('work_hours.exe' if windows else 'work_hours')))


if __name__ == '__main__':
    main()
