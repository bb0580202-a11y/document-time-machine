[中文](README.md) · **English**

# Document Time Machine

*The little undo button for the files you can't lose.*

It's two in the morning. Your essay won't open. The computer froze a minute ago, and the version that was working an hour ago is just — gone.

Unless someone had been quietly saving copies the whole time.

That someone is Document Time Machine. You point it at a folder — your Word files, your slides, your PDFs — and every time you press Save, it slips a copy somewhere safe, a place you never have to think about. Break a file, delete a file, or just wish you had yesterday's version back, and it's still there, waiting.

And it does all this without ever touching the file you're working on, and without sending a single thing over the internet. Everything stays on your own computer.

- **It stays with you.** No internet, no sign-up, no account. Nothing ever leaves your machine.
- **It only adds, never changes.** It keeps its own copies and never lays a finger on the file you're using.
- **It comes along.** The whole history hides inside the folder. Copy the folder to a USB stick, and every old version comes too.

> There's a command line **and** a real window, with a little icon that sits in your menu bar and can start itself when you log in. Just double-click to install on **both Mac and Windows** — it brings its own copy of git, so there's nothing else to set up.

## Getting it

Download the latest from [**Releases**](../../releases/latest):

- **Mac (Apple silicon):** get `doc-time-machine.dmg` (about 23 MB), double-click it, and follow [`docs/install-mac.md`](docs/install-mac.md) once the first time you open it.
- **Windows (x64):** get `doc-time-machine-windows-x64.zip`, unzip the **whole folder**, and double-click `doc-time-machine.exe` inside. (Keep the `_internal` folder right next to it — copying the .exe by itself won't work.)

> The apps aren't signed, and that's normal. On Mac, open it the first time with **right-click → Open** (or System Settings → "Open Anyway"). On Windows, if a blue SmartScreen box appears, click **More info → Run anyway**.

**Want to run it from the source code?** You'll need [git](https://git-scm.com/) and Python 3.10+:

```bash
pip install -e .                    # the command line, or start the window (python -m dtm.app.daemon)
bash scripts/build_mac.sh --dmg     # build the Mac .app + .dmg in one go (needs create-dmg)
```

## From the command line

| What you want | The command |
|---|---|
| Start watching a folder | `dtm init <folder>` |
| Watch it and save versions on its own | `dtm watch <folder>` (stays open; Ctrl+C to stop) |
| See every saved version | `dtm list <folder>` |
| Bring an old version back — saved *next to* the original, never on top of it | `dtm restore <folder> <version> <filename>` |
| Give a version a name you'll remember | `dtm tag <folder> <version> "before submission"` |
| Leave a little note on a version | `dtm note <folder> <version> "advisor: ending too weak"` |
| Start a new draft from an old version | `dtm branch <folder> <version>` |
| See how big the history has grown | `dtm stats <folder>` |
| Check that a file still opens | `dtm verify <folder>` |
| Make the history take up less room | `dtm gc <folder>` |
| Find the history again after moving the folder | `dtm relocate <folder>` |

The "version" is the short code in the square brackets at the start of each `dtm list` line.

## The window, and the helper that runs in the background

```bash
dtm daemon              # start the background helper: it watches your folders + sits in the menu bar
dtm autostart enable    # start it when you log in (macOS); also: disable, status
```

Click the little icon → **Open** to bring up the window:

- **The album** (the main page): one card for each version — your note as the title (or the time, if you didn't leave one), each file marked ▲ bigger or ▼ smaller, ★ for the ones you starred, and the exact second if you hover. Each card gives you three buttons: **Restore this version** (saved as a fresh copy *beside* the folder, never on top of what you're working on), leave a note, or star it.
- **The version tree** (a little map down the side): a timeline that folds long quiet days into "≈ no changes for N days" and gathers busy bursts together; if you ever started a second draft, each one gets its own lane. Click a spot to jump the album to it. It only opens itself when there's a real branch to show.
- When the helper saves a new version, the window **catches up within seconds** on its own (or press ↻).
- The top bar can also **📂 open the folder**, or **✕ stop watching** it (your files and history stay — one click to undo). After you restore, a little banner walks you straight to the copy it made.
- **It warns you when something's wrong.** If the history gets damaged — say the power cut out mid-save — a **red bar** appears at the top. And if the helper ever stopped without telling you, the next time you open the window a **yellow bar** says "there was a stretch back there that wasn't covered." It never lets you walk around thinking you're safe when you're not.

## What it keeps, and what it ignores

- **Keeps:** `.docx .xlsx .pptx .pdf .doc .xls .ppt .tex .md .txt .csv`
- **Ignores the clutter:** Office lock files (`~$…`), `.tmp`, `.DS_Store`, and the like.
- **Not sure about a file?** It keeps it anyway. Better a little clutter than one lost draft.

## The honest part: what it *can't* save you from (please read this)

It's great at "I broke it / I deleted it / I want the old one back." But a few things **no offline tool can fix**, and you should know them before you download (there's more in [`docs/这些情况它救不了.md`](docs/这些情况它救不了.md)):

- **A dead disk, or a laptop that's lost, stolen, or soaked in coffee.** The history lives on that one disk; if the disk is gone, so is everything on it. The only real shield is **a second copy somewhere else** — now and then, copy the whole folder onto a USB drive or the cloud. (Your copy brings its full history along.)
- **A bad spot on the disk that ruins one version.** That one version might be lost for good — though the others are usually fine. Same fix: keep that occasional second copy.
- **A file that was already broken when it was saved** (Word or your PDF reader crashed mid-save). It faithfully keeps whatever your computer wrote down; it can't un-break a file that was broken to begin with. But your earlier, good versions are safe — and it will **tell you plainly** when a version looks broken, instead of pretending it fixed it.

A couple of smaller things:

- Office files are stored whole, so it can tell you *which file, which version, bigger or smaller* — but not the exact sentence that changed between two drafts.
- Versions of a big file you edit a lot will pile up; run `dtm gc` any time to squeeze them. Trimming old versions further is for a later release.

## License

This project's own code is under the [MIT License](LICENSE). The third-party
components it bundles (git and others) keep their own licenses — see
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) (the bundled git is GPLv2,
with its source linked there).
