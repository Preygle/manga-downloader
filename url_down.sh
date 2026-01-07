BASE="https://ajinmanga.net"
MAIN="${BASE}/"

SITE_NAME=$(echo "$BASE" | sed -E 's#https?://(www\.)?([^/]+).*#\2#')
OUT_ROOT="./$SITE_NAME"

THREADS=32 # Number of parallel downloads (adjust as needed)

mkdir -p "$OUT_ROOT"

echo "Fetching chapter links..."
curl -s "$MAIN" \
  | grep -oiE '<a [^>]*href="[^"]*"' \
  | sed 's/.*href="\([^"]*\)".*/\1/' \
  | grep "/manga/ajin-chapter-" \
  | sort -u > chapters.txt

TOTAL=$(wc -l < chapters.txt | tr -d ' ')
echo "Found $TOTAL chapters."
echo "Saved to chapters.txt"

read -p "Press ENTER to start download..."

process_chapter() {
    local url="$1"

    if [[ "$url" =~ ^https?:// ]]; then
        FULL_URL="$url"
    else
        [[ "$url" == /* ]] || url="/$url"
        FULL_URL="${BASE}${url}"
    fi

    local chap=$(basename "$url")
    local OUT_DIR="$OUT_ROOT/$chap"

    mkdir -p "$OUT_DIR"

    echo ">>> Downloading $chap"

    curl -s "$FULL_URL" \
      | grep -oiE '<img[^>]+src="[^"]+"' \
      | sed 's/.*src="\([^"]*\)".*/\1/' \
      | grep -E '\.(jpg|jpeg|png|webp)' \
      | uniq > "$OUT_DIR/imglist.txt"

    local count=1
    while read -r img; do
        ext="${img##*.}"
        save_ext="${ext%%\?*}"
        curl -s "$img" -o "$OUT_DIR/$count.$save_ext"
        count=$((count+1))
    done < "$OUT_DIR/imglist.txt"

    rm "$OUT_DIR/imglist.txt"
    echo "<<< Finished $chap"
}

export -f process_chapter
export BASE OUT_ROOT

running=0

while read -r url; do
    process_chapter "$url" &

    ((running++))
    if (( running >= THREADS )); then
        wait -n
        ((running--))
    fi
done < chapters.txt

wait

echo "================================="
echo "All chapters downloaded."
echo "Saved under: $OUT_ROOT"
echo "================================="
