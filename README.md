# Manga Downloader & PDF Converter

A high-performance script suite to download manga chapters from web sources and convert them into PDF format.

## Features

- **Fast Parallel Downloads**: Utilizes multi-threading (default 32 threads) to download chapters simultaneously.
- **Automatic PDF Conversion**: Converts downloaded images into per-chapter PDFs.
- **One-Shot Execution**: Single `one_shot` script handles the entire workflow (download -> environment setup -> conversion).
- **Cross-Platform Compatibility**: Optimized for Windows (via native PowerShell) and Linux (via Bash).

## Quick Start (Windows)

The easiest way to run the tool on Windows is using the batch file.

### Prerequisites
- Windows 10/11 with PowerShell
- Python 3.x installed (make sure it's in your system PATH)

### Usage
1. **Run the script**:
   Double-click `one_shot.bat` or run it from your terminal:
   ```cmd
   .\one_shot.bat
   ```
2. **Follow the prompts**:
   - The script will ask where to start downloading (press ENTER for all chapters / type starting chapter number if needed).
3. **Wait**:
   - The script will download all images in parallel.
   - It will automatically create/activate a Python virtual environment (`venv`), install requirements, and convert images to PDFs.
4. **Output**:
   - Check the generated `*_pdf` directory (e.g., `read-monster.com_pdf`) for your completed PDF files.

## Quick Start (Linux / macOS)

### Prerequisites
- Bash environment
- Python 3.x installed

### Usage
1. **Run the script**:
   ```bash
   ./one_shot.sh
   ```
2. Follow the same prompts as above. Output will be in the corresponding `*_pdf` directory.

## How to Change the Manga

By default, the script is configured to download **Monster** from `https://read-monster.com/`. 

To download a different manga, you need to update **two values** in the downloader script: the **Base URL** and the **Chapter URL Filter**.

### Step 1: Identify the Website and Chapter Portion
Go to the manga website you want to use. 
- **Image 1 Reference:** Find a standard manga reading site (e.g., a site with a dark theme and chapter lists like the *Monster Manga Online* reference image you provided).
- **Image 2 Reference:** Click on any chapter and look at the URL in your browser. For example, if the URL is `read-monster.com/manga/monster-chapter-162/`, the portion that identifies a chapter is `/manga/monster-chapter-`.

### Step 2: Update the Windows Script (`url_down.ps1`)
Open `url_down.ps1` in a text editor and change these lines at the top:
```powershell
param (
    [string]$BaseUrl = "https://read-monster.com/", # <-- Change this to your new Base URL
    [int]$Threads = 32
)
```
Then, scroll down to the `$chapters` filter and update the `-match` string to match your new chapter portion:
```powershell
$chapters = ([regex]::Matches($html, $pattern) | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -match "/manga/monster-chapter-" } | Select-Object -Unique)
# Change "/manga/monster-chapter-" to your new target (e.g. "/manga/one-piece-chapter-")
```

### Step 3: Update the Linux Script (`url_down.sh`)
If you use the Bash version, open `url_down.sh` and change the top line:
```bash
BASE="https://read-monster.com/" # <-- Change this
```
And update the `grep` filter a few lines below:
```bash
  | grep "/manga/monster-chapter-" \ 
  # <-- Change this to your new chapter pattern
```

## Supported Websites

Designed and tested for sites like:
- `https://read-monster.com/` (Currently active)
- `https://readoshino.com/`
- `https://ajinmanga.net/`
- `https://w10.1punchman.com/`
- `https://chainsawmann.com/`

*Note: The script expects a standard HTML structure where chapters are linked via `<a href="...">` and images via `<img src="...">`. If a site uses dynamic JavaScript loading for images, the script may need adjustments.*

## Performance
Benchmarks for image-to-PDF conversion:
- **Sequential**: ~43.4s
- **Parallel (8 processes)**: ~16.8s

### Real-world Tests
- **80 Chapters processed in 93s**
- **Download Speed Test (100mbps)**:
    - **32 Threads**: ~4m 17s 
    - **8 Threads**: ~11m 30s 

Extraction is highly parallelized (32 threads by default), significantly reducing download time compared to sequential execution.

## Components

### `one_shot.bat` & `one_shot.sh`
The main orchestrators. They manage dependency installation (creates `venv` + `requirements.txt`) and chain the download and conversion steps.

### `url_down.ps1` & `url_down.sh`
The core downloader scripts.
- Scrapes chapter links.
- Downloads images in parallel.
- Outputs the download directory path for other scripts to use.

### `img_pdf.py`
The converter script.
- Converts downloaded chapter folders into single PDF files.
- Uses `multiprocessing` for speed.
- **Usage**:
  ```bash
  python img_pdf.py --input_folder "path/to/downloaded/manga"
  ```