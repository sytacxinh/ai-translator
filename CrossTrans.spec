# -*- mode: python ; coding: utf-8 -*-

# CrossTrans v1.9.0 - PyInstaller Build Configuration
# Build command: pyinstaller CrossTrans.spec --clean --noconfirm

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/assets', 'src/assets'),  # Icons and images
    ],
    hiddenimports=[
        # GUI framework
        'ttkbootstrap',
        'ttkbootstrap.dialogs',
        'ttkbootstrap.constants',
        'ttkbootstrap.style',
        'ttkbootstrap.themes',
        'ttkbootstrap.themes.standard',
        'ttkbootstrap.localization',
        'ttkbootstrap.icons',
        'ttkbootstrap.tooltip',
        'ttkbootstrap.scrolled',
        'ttkbootstrap.tableview',
        # Windows APIs
        'win32clipboard',
        'win32con',
        'win32api',
        'pywintypes',
        # Other dependencies
        'keyboard',
        'packaging',
        'packaging.version',
        'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce EXE size
        'pytest',
        'pytest_cov',
        'pytest_mock',
        # Note: unittest is needed by pyparsing.testing (used by httplib2/google-generativeai)
        'test',
        'tests',
        # Unused tkinter modules
        'tkinter.test',
        # Unused standard library
        'lib2to3',
    ],
    noarchive=False,
    optimize=1,  # Basic optimization
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CrossTrans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='CrossTrans.ico',
)
