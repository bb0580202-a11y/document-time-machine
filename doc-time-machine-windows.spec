# -*- mode: python ; coding: utf-8 -*-
# PyInstaller Windows 打包描述【草稿，未验证——待首次 GitHub Actions CI 跑通】。
# 镜像 doc-time-machine.spec(Mac)，差异已逐条标注。目标 = GitHub windows-latest(x64)。
#
# 便携 git：MinGit 由 scripts/build_windows.ps1 拉到 build/win-git/。
#   MinGit 布局 = cmd/git.exe + mingw64/...（与 Mac 的 bin/git 不同！）
#   => 资源进 _MEIPASS/git/ 后,git.exe 在 _MEIPASS/git/cmd/git.exe。
#
# ✅ 配套已改：dtm/app/runtime.py 的 bundled_git_path() 已加 win 分支(返回 <root>/git/cmd/git.exe),
#   有 test_runtime 两条平台分支单测护着(Mac 上也验过逻辑)。此处布局须与之对上(git/ -> cmd/git.exe)。

# pywebview 的 EdgeChromium/WinForms 后端自带 WebView2 DLL(藏在 webview/lib/),PyInstaller 不会自动收 →
# 必须显式 collect,否则冻结后开窗黑屏/报缺 DLL。这是最可能的 CI 失败点,先预防。
# (注意:目标 Win 机还需装 WebView2 运行时——Win11 内置,老 Win10 可能要 Evergreen Bootstrapper。)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['dtm_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('dtm/app/web', 'web'),        # gui.py 用 _MEIPASS/web
        ('build/win-git', 'git'),      # runtime.py 用 _MEIPASS/git/cmd/git.exe(Windows 分支)
        *collect_data_files('webview'),  # pywebview 自带 WebView2 DLL/资源(winforms 后端必需)
    ],
    hiddenimports=[
        'pystray._win32',              # 托盘 Windows 后端(Mac 是 _darwin)
        'webview.platforms.winforms',  # pywebview Windows 后端(Mac 是 cocoa);EdgeChromium 经此
        'clr_loader',                  # pythonnet 加载 .NET CLR(winforms 后端依赖)
        *collect_submodules('clr_loader'),
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
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
    # 无 target_arch:GitHub windows-latest 是 x64;Windows 目标=x64(多数用户),非 Mac 的 arm64-only
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='doc-time-machine')
# 无 BUNDLE：.app 是 macOS 专属。Windows 产物 = dist/doc-time-machine/ 文件夹(含 doc-time-machine.exe)。
