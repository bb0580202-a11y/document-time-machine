#!/usr/bin/env bash
# 可复现构建:macOS arm64 .app(默认) / .dmg(加 --dmg)。从 repo 根跑: bash scripts/build_mac.sh [--dmg]
# 产物落 gitignored build/ + dist/。不依赖 /tmp。
# 前置:CLT 已装(便携 git 源);python3;出 .dmg 还需 create-dmg(brew install create-dmg)。
set -euo pipefail
cd "$(dirname "$0")/.."                         # 切到 repo 根
CLT_GIT="/Library/Developer/CommandLineTools/usr/bin/git"

# ---------- 1/4 组装便携 git(lipo thin arm64,保 symlink 布局) ----------
echo "[1/4] 组装便携 git → build/mac-git"
[ -x "$CLT_GIT" ] || { echo "✗ 找不到 CLT git($CLT_GIT)。先 xcode-select --install"; exit 1; }
CLT_USR="$(dirname "$(dirname "$CLT_GIT")")"    # .../CommandLineTools/usr
rm -rf build/mac-git
mkdir -p build/mac-git/bin build/mac-git/libexec build/mac-git/share
lipo "$CLT_GIT" -thin arm64 -output build/mac-git/bin/git   # 源是 universal,瘦成 arm64
cp -Rp "$CLT_USR/libexec/git-core" build/mac-git/libexec/   # -R 不解引用(保 symlink) -p 保模式
cp -Rp "$CLT_USR/share/git-core"   build/mac-git/share/
GIT_VER="$("$CLT_GIT" --version)"
echo "    内置 git 版本(随构建机 CLT、未 pin): $GIT_VER"

# ---------- 2/4 干净最小 venv(体积根治:不含计量栈) ----------
echo "[2/4] 建干净最小 venv → build/venv-build"
rm -rf build/venv-build
python3 -m venv build/venv-build
build/venv-build/bin/pip -q install --upgrade pip
build/venv-build/bin/pip -q install -r requirements-build.txt
build/venv-build/bin/pip -q install -e . --no-deps   # dtm 可 import,依赖已 pin 装好、不重解析

# ---------- 3/4 PyInstaller 冻结 ----------
echo "[3/4] PyInstaller 冻结 → dist/doc-time-machine.app"
rm -rf build/doc-time-machine dist/doc-time-machine.app
build/venv-build/bin/pyinstaller --noconfirm doc-time-machine.spec

# ---------- 4/4 (可选)出 .dmg(拖拽布局) ----------
if [ "${1:-}" = "--dmg" ]; then
  command -v create-dmg >/dev/null || { echo "✗ 需 create-dmg: brew install create-dmg"; exit 1; }
  echo "[4/4] 打 .dmg → dist/doc-time-machine.dmg"
  rm -f dist/doc-time-machine.dmg
  create-dmg \
    --volname "doc-time-machine" \
    --window-size 540 380 --icon-size 100 \
    --icon "doc-time-machine.app" 140 190 \
    --app-drop-link 400 190 \
    dist/doc-time-machine.dmg dist/doc-time-machine.app
  echo "    .dmg 大小: $(du -sh dist/doc-time-machine.dmg | cut -f1)"
else
  echo "[4/4] 跳过 .dmg(加 --dmg 出盘)"
fi

echo "✓ 完成。.app 大小: $(du -sh dist/doc-time-machine.app | cut -f1)  (git: ${GIT_VER})"
