# Manga Downloader & PDF Converter

A high-performance script suite to download manga chapters from web sources and convert them into PDF format.

## Features

- **Fast Parallel Downloads**: Utilizes multi-threading (default 32 threads) to download chapters simultaneously.
- **Automatic PDF Conversion**: Converts downloaded images into per-chapter PDFs.
- **One-Shot Execution**: Single `one_shot.sh` script handles the entire workflow (download -> environment setup -> conversion).
- **Cross-Platform Compatibility**: Optimized for Windows (Git Bash/WSL) and Linux.

## Quick Start

The easiest way to use the tool is via the `one_shot.sh` runner script.

### Prerequisites
- Bash environment (Git Bash on Windows, or Linux/macOS)
- Python 3.x installed

### Usage
1.  **Run the script**:
    ```bash
    ./one_shot.sh
    ```
2.  **Follow the prompts**:
    - The script will ask where to start downloading (press ENTER for all chapters / type starting chapter number if needed).
3.  **Wait**:
    - The script will download all images.
    - It will automatically create/activate a `venv`, install requirements, and convert images to PDFs.
4.  **Output**:
    - Check the `*_pdf` directory (e.g., `readoshino.com_pdf`) for your files.

## Supported Websites
Designed primarily for:
- `https://readoshino.com/` (Currently active)
- `https://ajinmanga.net/`

Should work with sites having similar HTML structure, such as:
- `https://w10.1punchman.com/`
- `https://chainsawmann.com/`

*Note: To download from other sites, you may need to modify the `BASE` variable and grep patterns in `url_down.sh`.*

## Performance
Benchmarks for image-to-PDF conversion:
- **Sequential**: ~43.4s
- **Parallel (8 processes)**: ~16.8s

### Real-world Tests
- **80 Chapters processed in 93s**
- **Download Speed Test (100mbps)**:
    - **32 Threads**: ~4m 17s 
    - **8 Threads**: ~11m 30s 

Extraction is highly parallelized (32 threads), significantly reducing download time compared to sequential execution.

## Components

### `one_shot.sh`
The main orchestrator. It manages dependency installation (creates `venv` + `requirements.txt`) and chains the download and conversion steps.

### `url_down.sh`
The core downloader script.
- Scrapes chapter links.
- Downloads images in parallel.
- Outputs the download directory path for other scripts to use.
- Change BASE url manually

### `img_pdf.py`
The converter script.
- Converts downloaded chapter folders into single PDF files.
- Uses `multiprocessing` for speed.
- **Usage**:
  ```bash
  python img_pdf.py --input_folder "path/to/downloaded/manga"
  ```