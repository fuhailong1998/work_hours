# Build on the target OS/architecture. Only public static assets are bundled.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis(
    [str(root / 'server.py')], pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'web' / 'index.html'), 'web'),
           (str(root / 'web' / 'favicon.svg'), 'web'),
           (str(root / 'web' / 'static'), 'web/static'),
           (str(root / 'data' / 'holidays'), 'data/holidays')],
    hiddenimports=['PIL.Image', 'PIL.PngImagePlugin'],
    excludes=['playwright', 'selenium', 'tkinter', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='work_hours',
          debug=False, strip=False, upx=False, console=True)
