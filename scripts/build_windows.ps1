# Windows 构建脚本【草稿，未验证——待首次 GitHub Actions CI 跑通】。镜像 scripts/build_mac.sh 四步。
# 跑法(CI windows-latest 或 本地 Win)：  pwsh scripts/build_windows.ps1
# 产物：dist/doc-time-machine/doc-time-machine.exe（整个文件夹自带一切,拷 U 盘即可在离线 Win 跑）。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)   # 切 repo 根

# ---------- 1/4 拉便携 git(MinGit) -> build/win-git ----------
# MinGit 64-bit(非 busybox)。2026-06-04 经 gh api 查得最新 v2.54.0.windows.1;日后可再核 git-for-windows releases。
$mingitUrl = "https://github.com/git-for-windows/git/releases/download/v2.54.0.windows.1/MinGit-2.54.0-64-bit.zip"
Write-Host "[1/4] 拉 MinGit -> build/win-git"
Remove-Item -Recurse -Force build/win-git -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force build | Out-Null
Invoke-WebRequest $mingitUrl -OutFile build/mingit.zip
Expand-Archive build/mingit.zip -DestinationPath build/win-git -Force
# 验证 git.exe 真在（MinGit 布局 cmd/git.exe）
if (-not (Test-Path build/win-git/cmd/git.exe)) { throw "MinGit 布局异常:没找到 cmd/git.exe" }

# ---------- 1.5/4 瘦身:删 dtm 用不到的部件(纯本地零联网 INV-4) ----------
# dtm 永不登录/不连 remote → Git 凭据管理器(GCM)的整套 .NET GUI 栈(Avalonia/Skia/MSAL)是死代码;
# git.exe 是原生 C、不加载任何 .NET → 删它们零风险。绝不删 git.exe 依赖的原生 DLL
# (libcrypto/libcurl/libssl/... 全保留,免 git.exe 加载失败)。删完当场 git --version 自检。
Write-Host "[1.5/4] 瘦身:删 GCM/.NET 栈 + scalar + 文档(dtm 零联网用不到)"
$bin = "build/win-git/mingw64/bin"
$drop = @(
  "git-credential-manager.exe", "scalar.exe",
  "Avalonia*.dll", "SkiaSharp.dll", "libSkiaSharp.dll", "HarfBuzzSharp.dll", "libHarfBuzzSharp.dll",
  "av_libglesv2.dll", "msalruntime*.dll", "gcmcore.dll",
  "Microsoft.Identity*.dll", "Microsoft.IdentityModel*.dll", "Microsoft.AzureRepos.dll", "Microsoft.Bcl*.dll",
  "System.*.dll"
)
$before = (Get-ChildItem build/win-git -Recurse -File | Measure-Object Length -Sum).Sum
foreach ($pat in $drop) { Remove-Item -Force "$bin/$pat" -ErrorAction SilentlyContinue }
foreach ($d in @("mingw64/share/doc","mingw64/share/git-gui","mingw64/share/gitk","mingw64/share/locale","mingw64/doc")) {
  Remove-Item -Recurse -Force "build/win-git/$d" -ErrorAction SilentlyContinue
}
# 激进档:删 usr/(MSYS shell:bash/perl/coreutils)——dtm 只调 git 原生 builtin、不走 shell。
# 有风险,故下面用真 git 操作冒烟测兜底:删坏任一操作=CI 失败=不出坏包。
Remove-Item -Recurse -Force "build/win-git/usr" -ErrorAction SilentlyContinue
$after = (Get-ChildItem build/win-git -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("    内置 git: {0:N0}MB -> {1:N0}MB (省 {2:N0}MB)" -f ($before/1MB), ($after/1MB), (($before-$after)/1MB))

# 冒烟测:跑一遍 dtm 真实用到的所有 git 操作,验瘦身没删坏任何东西
Write-Host "    冒烟测:跑 dtm 用到的 git 操作..."
$g = (Resolve-Path "build/win-git/cmd/git.exe").Path
$tmp = "build/git-smoke"; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $tmp | Out-Null
$ok = $true
function Chk($desc) { if ($LASTEXITCODE -ne 0) { Write-Host "      ✗ $desc"; $script:ok = $false } }
& $g -C $tmp init -q; Chk "init"
& $g -C $tmp config user.email "x@dtm"; & $g -C $tmp config user.name "dtm"
& $g -C $tmp config core.filemode false; & $g -C $tmp config core.autocrlf false; Chk "config"
Set-Content "$tmp/a.txt" "hello"; & $g -C $tmp add -A; Chk "add"
& $g -C $tmp commit -q -m "t1" 2>&1 | Out-Null; Chk "commit"
& $g -C $tmp rev-parse HEAD | Out-Null; Chk "rev-parse"
& $g -C $tmp log --branches --format=%H | Out-Null; Chk "log"
& $g -C $tmp notes --ref=refs/notes/dtm add -f -m "note" HEAD 2>&1 | Out-Null; Chk "notes add"
& $g -C $tmp notes --ref=refs/notes/dtm show HEAD | Out-Null; Chk "notes show"
& $g -C $tmp tag -f mytag HEAD 2>&1 | Out-Null; Chk "tag"
& $g -C $tmp for-each-ref --format="%(objectname)" refs/tags | Out-Null; Chk "for-each-ref"
& $g -C $tmp show --name-only --format= HEAD | Out-Null; Chk "show"
& $g -C $tmp cat-file -s HEAD:a.txt | Out-Null; Chk "cat-file"
if (-not $ok) { throw "瘦身冒烟测失败:某个 git 操作删坏了,不出坏包。回退 usr/ 删除再来。" }
Write-Host "    ✓ 冒烟测全过,瘦身安全"

# ---------- 2/4 干净最小 venv（体积根治:不含计量栈）----------
Write-Host "[2/4] 建干净最小 venv -> build/venv-build"
Remove-Item -Recurse -Force build/venv-build -ErrorAction SilentlyContinue
python -m venv build/venv-build
build/venv-build/Scripts/pip install --upgrade pip
build/venv-build/Scripts/pip install -r requirements-build-windows.txt
build/venv-build/Scripts/pip install -e . --no-deps

# ---------- 3/4 PyInstaller 冻结 ----------
Write-Host "[3/4] PyInstaller 冻结 -> dist/doc-time-machine/"
Remove-Item -Recurse -Force dist/doc-time-machine -ErrorAction SilentlyContinue
build/venv-build/Scripts/pyinstaller --noconfirm doc-time-machine-windows.spec

# 把说明 + 协议放进包(解压即见,GPL/第三方合规)
Copy-Item "docs/使用说明.txt","LICENSE","THIRD_PARTY_LICENSES.md" -Destination "dist/doc-time-machine/" -Force

# ---------- 4/4 产出 ----------
if (-not (Test-Path dist/doc-time-machine/doc-time-machine.exe)) { throw "没产出 .exe" }
if (-not (Test-Path "dist/doc-time-machine/使用说明.txt")) { throw "使用说明.txt 没进包" }
Write-Host "[4/4] 完成: dist/doc-time-machine/doc-time-machine.exe（含使用说明 + 协议）"
# 安装器(Inno Setup 等)留待后续；先有自带一切的文件夹即可拷 U 盘测试。
