<p align="center">
  <img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/logo.png" width="84" alt="MangaBinder logo">
</p>

<h1 align="center">MangaBinder</h1>

<p align="center">
  Download manga chapters, convert them to PDF, bind them into volumes and export CBZ,<br>
  from a friendly browser interface or a single command.
</p>

<p align="center">
  <a href="https://pypi.org/project/mangabinder/"><img src="https://img.shields.io/pypi/v/mangabinder?color=3b5bdb" alt="PyPI"></a>
  <a href="https://github.com/Preygle/manga-downloader/releases/latest"><img src="https://img.shields.io/github/v/release/Preygle/manga-downloader?label=windows%20.exe&color=3b5bdb" alt="Windows download"></a>
  <img src="https://img.shields.io/pypi/pyversions/mangabinder" alt="Python versions">
  <a href="https://github.com/Preygle/manga-downloader/actions/workflows/ci.yml"><img src="https://github.com/Preygle/manga-downloader/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/screenshot-overview.png" width="900" alt="MangaBinder web interface with the main features annotated">
</p>

## Features

- **Parallel downloads.** Finds every chapter on a series page and downloads many chapters at once.
- **Resume anywhere.** Progress is saved, so an interrupted download picks up where it stopped.
- **Chapter PDFs.** Each chapter becomes one PDF. Re-runs only rebuild chapters that changed.
- **Volume PDFs.** Chapters are bound into volumes using real volume data from MangaDex / AniList, with a bookmark for every chapter.
- **CBZ export.** For e-readers and comic apps. Two-page spreads are split in right-to-left order.
- **Browser interface.** Run everything, watch live progress, and read your volumes in the browser.
- **Nothing extra to install.** A standalone Windows `.exe`, or `pip install` on Windows, macOS and Linux. No Poppler, no Ghostscript.

## Install

Pick whichever you already use. Every option gives you the same `mangabinder` command.

| Platform | Install with | Command |
| --- | --- | --- |
| Windows | **winget** | `winget install Preygle.MangaBinder` |
| Windows | **Scoop** | `scoop bucket add preygle https://github.com/Preygle/scoop-bucket`<br>`scoop install mangabinder` |
| Windows | **Chocolatey** | `choco install mangabinder` |
| Windows | **Download** | [`mangabinder.exe`](https://github.com/Preygle/manga-downloader/releases/latest), no install needed |
| macOS / Linux | **Homebrew** | `brew install preygle/tap/mangabinder` |
| Any OS | **pipx / pip** | `pipx install mangabinder` (Python 3.9+) |
| Any OS | **conda** | `conda install -c conda-forge mangabinder` |
| Arch Linux | **AUR** | `yay -S mangabinder` |
| Server / NAS | **Docker** | see [Docker](#docker) |

> winget, Chocolatey and conda-forge review new packages by hand. If one of those commands can't find
> `mangabinder` yet, its review is still in progress; use another option meanwhile.

Then run `mangabinder web` for the browser interface, or use the [command line](#command-line).

**Using the `.exe` directly:** double-click it and the web interface opens, with downloads going to `Documents\MangaBinder`.
Windows SmartScreen may warn about an unrecognised app because the `.exe` isn't code-signed. Click **More info → Run anyway**.

### Docker

Run the web interface on a server or NAS and open it from any device on your network:

```bash
docker run -d --name mangabinder -p 8765:8765 -v ~/Manga:/library ghcr.io/preygle/mangabinder
```

Then browse to `http://<server-ip>:8765`. The page has no login, so don't expose that port to the internet.
CLI commands work too:

```bash
docker run --rm -v ~/Manga:/library -w /library ghcr.io/preygle/mangabinder download URL --volumes
```

## Using the web interface

```bash
mangabinder web                          # opens http://127.0.0.1:8765
mangabinder web --library D:\Manga       # keep downloads somewhere else
mangabinder web --host 0.0.0.0           # also reachable from other devices (no login!)
```

### 1. Download

Paste the **series page**, the page on the site that links to every chapter. Then press **Download + convert to PDF**.

<img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/screenshot-download.png" width="820" alt="Download form with each option numbered and explained">

Chapter links like `…/chapter-12` are detected automatically. Fill in **Chapter link pattern** only if a site names its chapters differently (see [Supported sites](#supported-sites)).

### 2. Watch it run

The **Activity** panel streams the output of every job live. **Stop** cancels the current job. Resume is on by default, so pressing the button again later continues from where it stopped.

### 3. Read, merge and export

Everything you've downloaded appears in the **Library**:

<img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/screenshot-library.png" width="820" alt="Library panel with each action numbered and explained">

Click a volume to read it in your browser's PDF viewer. Each chapter is bookmarked:

<img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/screenshot-reader.png" width="820" alt="A merged volume open in the browser PDF viewer">

<details>
<summary><b>Dark mode</b> follows your system setting</summary>
<br>
<img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/screenshot-dark.png" width="700" alt="MangaBinder in dark mode">
</details>

## Command line

One command runs the whole pipeline: download, then chapter PDFs, then volumes.

```bash
mangabinder download https://example.com/manga/series-name/ --volumes
```

<img src="https://raw.githubusercontent.com/Preygle/manga-downloader/master/docs/screenshot-cli.png" width="900" alt="Terminal output of a full download, convert and merge run, annotated">

Or run each step on its own:

| Command | What it does |
| --- | --- |
| `mangabinder download URL` | Download every chapter into `./<site>/<chapter>/` |
| `mangabinder convert FOLDER` | Build `FOLDER_pdf/<chapter>.pdf` from the chapter images |
| `mangabinder merge FOLDER_pdf` | Bind chapter PDFs into `FOLDER_pdf_volumes/<Title> v01.pdf`, … |
| `mangabinder cbz PDF_FOLDER` | Convert PDFs (chapters or volumes) to CBZ in `PDF_FOLDER_cbz/` |
| `mangabinder web` | Open the browser interface |
| `mangabinder gui` | Small desktop window for PDF → CBZ |

Useful options (run `mangabinder <command> --help` for all of them):

```bash
# download
mangabinder download URL --pattern title-chapter-   # only follow links containing this text
mangabinder download URL --start 120                # skip chapters before 120
mangabinder download URL --threads 8                # gentler on the site (default 16)
mangabinder download URL --fresh                    # ignore saved progress
mangabinder download URL --convert                  # also make chapter PDFs

# volumes
mangabinder merge example.com_pdf --dry-run         # print the volume plan only
mangabinder merge example.com_pdf --title "Monster"  # when the guessed title is wrong
mangabinder merge example.com_pdf --series-id <id> --source mangadex

# cbz
mangabinder cbz example.com_pdf_volumes --dpi 200 --no-split
```

## How it works

### Output layout

```
Documents/MangaBinder/                 (or the folder you ran the command in)
├── example.com/                       downloaded images, one folder per chapter
│   ├── series-chapter-1/1.jpg, 2.jpg, …
│   └── download_state.txt             finished chapters, used to resume
├── example.com_pdf/                   one PDF per chapter
├── example.com_pdf_volumes/           one PDF per volume + volume_map.json
└── example.com_pdf_volumes_cbz/       CBZ files
```

### Supported sites

MangaBinder works with the common "online reader" layout:

- The series page links to each chapter with a normal link (`<a href="…/chapter-12/">`).
- Each chapter page shows its pages as images (`<img src>`, or lazy-loaded `data-src`).

If **no chapters are found**, open any chapter, look at its address, and pass the part every chapter link shares as the pattern. For example, for `https://site.com/manga/monster-chapter-162/` use `--pattern monster-chapter-`. Sites that load pages with JavaScript only, or that need a login, aren't supported.

> **Git Bash users:** a pattern starting with `/` gets rewritten into a Windows path by Git Bash.
> Leave off the leading slash (`monster-chapter-`) or run the command from PowerShell / cmd.

### Volume mapping

The series title is guessed from the chapter names (`monster-chapter-1` → *Monster*) and looked up on **MangaDex** and **AniList**. No API key is needed.

1. **MangaDex per-chapter volume data** is used when it covers at least 70% of the chapters. This is the accurate path.
2. **Even split** across the published volume count is the fallback when no per-chapter data exists. This is *approximate*, and the run prints a warning.

Each run writes `volume_map.json` into the volumes folder. **Edit the `mapping` (chapter → volume) and re-run**. A map file always wins over a new lookup, so your corrections stick. Lookups are cached in your user cache folder.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "No chapters found" | Pass `--pattern` (see [Supported sites](#supported-sites)), and check the URL is the series page, not a chapter |
| Some chapters failed | Run the same command again. Finished chapters and pages are skipped |
| Wrong series picked for volumes | `--title "Exact Name"`, or `--series-id` with the MangaDex id |
| Volume boundaries slightly off | Edit `volume_map.json` in the volumes folder and run `merge --overwrite` |
| Port 8765 already in use | `mangabinder web --port 9000` (it also tries the next 9 ports automatically) |

## Development

```bash
git clone https://github.com/Preygle/manga-downloader.git
cd manga-downloader
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Build the Windows executable locally:

```bash
pip install pyinstaller
pyinstaller --onefile --console --name mangabinder --icon packaging/icon.ico \
  --collect-all pypdfium2 --collect-all pypdfium2_raw packaging/entry.py
```

### Releasing

1. Bump `__version__` in `src/mangabinder/__init__.py` and merge to `master`.
2. `gh release create vX.Y.Z --generate-notes`

Publishing the release runs [`release.yml`](.github/workflows/release.yml), which ships it everywhere:

| Channel | How it's updated | One-time setup |
| --- | --- | --- |
| GitHub release | wheel, sdist and `mangabinder.exe` attached | none |
| PyPI | [trusted publishing](https://docs.pypi.org/trusted-publishers/) | pypi.org publisher: `Preygle` / `manga-downloader` / `release.yml` / env `pypi` |
| Docker | pushed to `ghcr.io/preygle/mangabinder` | none |
| Chocolatey | `choco push` | repo secret `CHOCOLATEY_API_KEY` |
| winget | `wingetcreate update` opens a PR to microsoft/winget-pkgs | repo secret `WINGET_TOKEN` (classic PAT, `public_repo`) |
| AUR | PKGBUILD pushed over SSH | repo secret `AUR_SSH_PRIVATE_KEY` |
| Scoop | [scoop-bucket](https://github.com/Preygle/scoop-bucket) checks for new releases every 6 hours | none |
| Homebrew | [homebrew-tap](https://github.com/Preygle/homebrew-tap) checks for new releases every 6 hours | none |
| conda-forge | the conda-forge bot opens a PR on the feedstock | none |

A channel whose secret is missing is still built and tested, just not published.

## Responsible use

MangaBinder is a general-purpose tool. Only download content you have the right to download, respect each site's terms of service, and support the creators by buying official releases where they're available.

## License

[MIT](LICENSE) © Mohammad Owais
