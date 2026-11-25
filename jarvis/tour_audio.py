"""Make the narration clips for the JARVIS tour, using the Mac's built-in `say` and `afconvert`.

    python3 jarvis/tour_audio.py            writes static/tour/<scene-id>.m4a for every scene
    python3 jarvis/tour_audio.py --voice Alex

Reads jarvis/static/tour/scenes.json. Run it again after editing a scene's "say" text.
Only the built-in macOS tools run, with arguments passed as lists (never a shell string).
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOUR = HERE / "static" / "tour"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the JARVIS tour narration with say.")
    ap.add_argument("--voice", default="Samantha", help="a voice from `say -v '?'` (default: Samantha)")
    a = ap.parse_args(argv)
    scenes = json.loads((TOUR / "scenes.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        for s in scenes:
            aiff = Path(tmp) / (s["id"] + ".aiff")
            out = TOUR / (s["id"] + ".m4a")
            subprocess.run(["say", "-v", a.voice, "-o", str(aiff), s["say"]], check=True)
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(aiff), str(out)], check=True)
            print("%-10s %s" % (s["id"], out.name))
    print("Wrote %d narration clips to %s" % (len(scenes), TOUR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
