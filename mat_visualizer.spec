# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# 数据文件包含列表
datas = [
    ('frontend/html', 'frontend/html'),
    ('frontend/js', 'frontend/js'),
    ('frontend/css', 'frontend/css'),
]

# 二进制文件包含列表
binaries = []

# 隐藏导入
hiddenimports = [
    'scipy',
    'scipy.special',
    'scipy._lib',
    'scipy._lib.messagestream',
    'h5py',
    'h5py._errors',
    'h5py.defs',
    'h5py.h5',
    'h5py.h5z',
    'h5py.utils',
    'numpy',
    'numpy.core',
    'numpy.core._methods',
    'numpy.core._dtype_ctypes',
    'numpy.random',
    'flask',
    'werkzeug',
    'jinja2',
    'markupsafe',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MAT_Visualizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
