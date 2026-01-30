#!/bin/bash

# one_shot.sh - Manga Downloader & Converter Pipeline
# Usage: ./one_shot.sh

echo "=========================================="
echo " Starting Manga Downloader Pipeline"
echo "=========================================="

# 1. Run the downloader and capture output
echo ">> Running Downloader..."
# We use a temporary file to capture output because we want to see it live AND capture it.
# 'tee' allows us to see it, but capturing into a variable hides it until done.
# Since url_down.sh is interactive, we need it to be attached to terminal.
# We will just redirect stdout to a file for parsing, but keep stderr or rely on tee.
# A simple way for interactive scripts is to let it run, and just grep the file after.

OUTPUT_LOG="downloader_output.log"
# We need to make sure we can handle user input. 
# Piping to tee might buffer or mess up 'read -p', but usually it works if not extremely strict.
# Better approach: Run script, let it finish, then read the last few lines of the log?
# Or just run it normally and also append output to a log file?
# 'script' command is good for this but not always available on minimal windows-bash.

# Let's try simple redirection with tee.
./url_down.sh | tee "$OUTPUT_LOG"

# 2. Extract Output Directory
# We look for the specific marker we added: "OUTPUT_DIR_PATH::..."
CAPTURED_DIR=$(grep "OUTPUT_DIR_PATH::" "$OUTPUT_LOG" | tail -n 1 | sed 's/OUTPUT_DIR_PATH:://')

# Clean up log if desired, or keep it.
rm "$OUTPUT_LOG"

if [ -z "$CAPTURED_DIR" ]; then
    echo "Error: Could not determine download directory from url_down.sh output."
    echo "Make sure the download finished successfully."
    exit 1
fi

# Remove carriage returns if any (common in Windows)
CAPTURED_DIR=$(echo "$CAPTURED_DIR" | tr -d '\r')

echo ">> Detected Download Directory: '$CAPTURED_DIR'"

# 3. Environment Setup
echo ">> Checking Environment..."

VENV_DIR="venv"
PYTHON_CMD="python"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR" || { echo "Failed to create venv"; exit 1; }
fi

# Activate venv
# On Windows Git Bash, Scripts/activate is valid. On WSL, bin/activate.
if [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
elif [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "Warning: Could not find activate script. Trying to use direct python path."
fi

# Determine python path inside venv just to be safe if activation failed (but we sourced it)
if [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON_EXEC="$VENV_DIR/Scripts/python.exe"
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON_EXEC="$VENV_DIR/bin/python"
else
    PYTHON_EXEC="python" # Fallback
fi

echo ">> Installing Requirements..."
"$PYTHON_EXEC" -m pip install -r requirements.txt

# 4. Run Converter
echo ">> Running PDF Converter..."
"$PYTHON_EXEC" img_pdf.py --input_folder "$CAPTURED_DIR"

echo "=========================================="
echo " Pipeline Finished Successfully"
echo "=========================================="
