# Third-Party Licenses

Document Time Machine's own code is under the MIT License (see [`LICENSE`](LICENSE)).
Its distributed builds (the macOS `.dmg` and the Windows `.zip`) also bundle the
third-party software listed below. Each remains under its own license; this file
collects the notices those licenses require.

## git (bundled) — GPLv2

The app bundles a copy of **git** so it works without a separate install.

- **macOS build:** git 2.50.1 (Apple Git-155), taken from the Apple Command Line Tools.
- **Windows build:** MinGit, from Git for Windows.

git is licensed under the **GNU General Public License, version 2 (GPLv2)**. As
required by the GPL, the complete corresponding source code for the bundled
version is available at:

- Upstream git source (v2.50.1): <https://github.com/git/git/tree/v2.50.1>
- Apple's published source (Apple Git-155): <https://opensource.apple.com/>
- Git for Windows / MinGit source: <https://github.com/git-for-windows/git>

This serves as a written offer, valid for as long as these builds are
distributed, to obtain the corresponding source of the bundled git. The full
GPLv2 text is at <https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt>.

git is invoked as a **separate program** (via its command line); the rest of
Document Time Machine is a separate work under the MIT License. Bundling them
together is mere aggregation and does not place this project under the GPL.

## Python runtime — PSF License

The Python interpreter is bundled by PyInstaller, under the Python Software
Foundation License: <https://docs.python.org/3/license.html>

## Bundled Python packages

| Package | Version | License | Source |
|---|---|---|---|
| pywebview | 6.2.1 | BSD-3-Clause | <https://github.com/r0x0r/pywebview> |
| pystray | 0.19.5 | LGPL-3.0 | <https://github.com/moses-palmer/pystray> |
| watchdog | 6.0.0 | Apache-2.0 | <https://github.com/gorakhargosh/watchdog> |
| Pillow | 10.4.0 | HPND (MIT-CMU) | <https://github.com/python-pillow/Pillow> |
| six | 1.17.0 | MIT | <https://github.com/benjaminp/six> |
| pyobjc (core, Cocoa, Quartz) | 12.2 | MIT | <https://github.com/ronaldoussoren/pyobjc> *(macOS build)* |
| pythonnet | 3.x | MIT | <https://github.com/pythonnet/pythonnet> *(Windows build)* |

**pystray** is under the LGPL-3.0. It is included as a standard, separately
replaceable Python module; its source is available at the link above.

## Build tool — PyInstaller (GPLv2 with bootloader exception)

PyInstaller is used only to build the app. Its bootloader carries an explicit
exception that permits distributing the frozen application under any license, so
it imposes no license requirement on Document Time Machine.
<https://github.com/pyinstaller/pyinstaller>

## Microsoft Edge WebView2 (Windows only)

The Windows build renders its window with the Microsoft Edge WebView2 runtime
provided by the operating system, under Microsoft's distributable-code terms.
