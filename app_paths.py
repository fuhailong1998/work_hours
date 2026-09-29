"""Read-only packaged resources and persistent, per-user application data."""
import os
from pathlib import Path
import sys

RESOURCE_ROOT = Path(__file__).resolve().parent


def data_root():
    override = os.environ.get('WORK_HOURS_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if not getattr(sys, 'frozen', False):
        return RESOURCE_ROOT / '.local'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'work_hours'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'work_hours'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'work_hours'


DATA_ROOT = data_root()
