# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包描述(Spike 1)。仅 macOS arm64;Windows 走 Task C(待 Win 机)。
#
# 便携 git:Spike0 把 CLT 真 git 树放在 build/mac-git/(gitignored)。
# 构建前需:  cp -R /tmp/dtm-portable-git build/mac-git   (Plan2 再落成可复现构建脚本)
#
# 资源去向(经 sys._MEIPASS,见 app/runtime.py 与 app/gui.py):
#   前端  dtm/app/web  -> _MEIPASS/web
#   便携git build/mac-git -> _MEIPASS/git  (=> _MEIPASS/git/bin/git)

a = Analysis(
    ['dtm_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('dtm/app/web', 'web'),        # gui.py 用 _MEIPASS/web
        ('build/mac-git', 'git'),      # runtime.py 用 _MEIPASS/git/bin/git
    ],
    hiddenimports=[
        'pystray._darwin',             # 托盘 macOS 后端
        'webview.platforms.cocoa',     # pywebview macOS 后端
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 纵深第二道:干净 venv(scripts/build_mac.sh)已从源头不装这些,
        # 此处再挡一层,防 Pillow 等钩子把可选 numpy/tkinter 集成二次拽入。
        'numpy', 'scipy', 'pandas', 'matplotlib', 'statsmodels',
        'tkinter', '_tkinter',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='doc-time-machine',
    debug=False,
    strip=False,
    upx=False,
    console=False,                     # GUI app,不开终端窗
    target_arch='arm64',               # 只 arm64(Intel 不支持,见设计)
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='doc-time-machine')

app = BUNDLE(
    coll,
    name='doc-time-machine.app',
    icon=None,
    bundle_identifier='com.doc-time-machine',
)
