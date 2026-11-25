#!/bin/sh
# Regenerate everything in docs/ and the demo schematic PDF:
#   docs/demo-board/*.svg, schematics/DEMO_Schematic.pdf, docs/images/*.png and ask.gif
#
#   sh docs/tools/make-media.sh        (from the repo root)
#
# Needs Python 3.9+, Node 22+ (built-in WebSocket), Google Chrome, ffmpeg, and Claude Code logged in:
# the screenshots show real answers. It runs JARVIS on a temporary data folder, so your logs are untouched.
set -eu
cd "$(dirname "$0")/../.."
CHROME=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}
PORT=${PORT:-8799}
DT=${DT:-9333}
T=$(mktemp -d)
SRV=""; CH=""
trap 'kill $SRV $CH 2>/dev/null || true' EXIT

echo "1/5 demo board drawings"
python3 docs/tools/schematic.py > docs/demo-board/schematic.svg
python3 docs/tools/pcb.py > docs/demo-board/pcb.svg

echo "2/5 schematic PDF and board photo"
cp docs/demo-board/schematic.svg "$T/"
printf '<!doctype html><meta charset="utf-8"><title>DEMO-1 schematic</title><style>@page{size:1200px 770px;margin:0}html,body{margin:0}img{display:block;width:1200px;height:770px}</style><img src="schematic.svg">' > "$T/print.html"
"$CHROME" --headless=new --disable-gpu --no-first-run --user-data-dir="$T/p1" --no-pdf-header-footer \
  --print-to-pdf="$PWD/schematics/DEMO_Schematic.pdf" "file://$T/print.html" 2>/dev/null
"$CHROME" --headless=new --disable-gpu --no-first-run --user-data-dir="$T/p1" --hide-scrollbars \
  --window-size=980,660 --screenshot="$T/pcb.png" "file://$PWD/docs/demo-board/pcb.svg" 2>/dev/null

echo "3/5 demo week (temporary data folder)"
D="$T/data"
mkdir -p "$D/reference"
cp jarvis/reference/DEMO_A*.csv "$D/reference/"
JARVIS_DATA_DIR="$D" python3 -c "import sys; sys.path.insert(0, 'jarvis'); import capture; capture.api_token()"
JARVIS_DATA_DIR="$D" python3 jarvis/server.py --port "$PORT" > "$T/server.log" 2>&1 & SRV=$!
sleep 3
python3 docs/tools/seed.py "$PORT" "$D" "$T/pcb.png"
JARVIS_DATA_DIR="$D" python3 jarvis/backup.py --dest "$T/backup" > /dev/null
# Show a typical backup folder instead of the temp path.
python3 -c "import json,sys; p=sys.argv[1]; s=json.load(open(p)); s['backup_dest']='/Volumes/BENCHUSB/jarvis'; json.dump(s, open(p,'w'))" "$D/settings.json"

echo "4/5 screenshots (real brain, a few minutes)"
"$CHROME" --headless=new --disable-gpu --no-first-run --no-default-browser-check --user-data-dir="$T/p2" \
  --remote-debugging-port="$DT" --hide-scrollbars about:blank > /dev/null 2>&1 & CH=$!
sleep 2
node docs/tools/shoot.mjs "http://127.0.0.1:$PORT/" "$DT" "$T/out"

echo "5/5 resize, palette, GIF"
for n in ask-source log seen board debrief review health boot; do
  ffmpeg -v error -y -i "$T/out/$n.png" -vf "scale=1600:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=none" \
    -pix_fmt pal8 "docs/images/$n.png"
done
mkdir -p "$T/gif"
set -- $(ls "$T/out/frames")
total=$#; stream=$((total - 6)); i=0; n=0
for f in "$@"; do
  if [ $i -lt $((stream - 1)) ] && [ $((i % 3)) -eq 0 ]; then cp "$T/out/frames/$f" "$T/gif/g$(printf %04d $n).png"; n=$((n + 1)); fi
  [ $i -eq $((stream - 1)) ] && answer=$f
  i=$((i + 1)); last=$f
done
for k in 1 2 3 4 5; do cp "$T/out/frames/$answer" "$T/gif/g$(printf %04d $n).png"; n=$((n + 1)); done
for k in 1 2 3 4 5 6 7 8 9 10 11 12; do cp "$T/out/frames/$last" "$T/gif/g$(printf %04d $n).png"; n=$((n + 1)); done
ffmpeg -v error -y -framerate 2.5 -i "$T/gif/g%04d.png" \
  -vf "scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
  docs/images/ask.gif
echo "Done. Check docs/images/ before committing: the answers are real, so they change between runs."
