"""JARVIS backup: copy your bench data to a folder you choose once.

    sh jarvis.sh backup                   back up to the saved folder (asks once if none is saved)
    sh jarvis.sh backup --dest PATH       set (and remember) the folder, then back up
    sh jarvis.sh backup --status          show the saved folder and the last backup

Copies logs (with photos, close-outs, usage), debriefs, reference ranges, evals, drafts and settings.json
into <dest>/jarvis-backup-YYYY-MM-DD_HHMMSS/. Keeps the 10 newest copies and deletes older ones. It only
ever deletes folders it created (that exact name pattern). Nothing is sent anywhere.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture  # noqa: E402
import store  # noqa: E402

KEEP = 10
STALE_DAYS = 7
NAME_RE = re.compile(r"^jarvis-backup-\d{4}-\d{2}-\d{2}_\d{6}$")
DIRS = ("logs", "debriefs", "reference", "evals", "drafts")


def _dest_ok(dest):
    dest = Path(os.path.expanduser(str(dest))).resolve()
    for inside in (store.REPO.resolve(), store.DATA_DIR.resolve()):
        if dest == inside or inside in dest.parents:
            raise ValueError("Pick a folder outside the repo and outside JARVIS's data folder: %s" % dest)
    return dest


def status(now=None):
    s = capture.load_settings()
    last = s.get("last_backup")
    now = now or dt.datetime.now()
    age = None
    if last:
        try:
            age = (now - dt.datetime.fromisoformat(last)).days
        except ValueError:
            last = None
    return {"dest": s.get("backup_dest"), "last": last, "age_days": age,
            "stale": last is None or age > STALE_DAYS, "stale_days": STALE_DAYS}


def run(dest=None, now=None):
    s = capture.load_settings()
    dest = str(dest or s.get("backup_dest") or "").strip()
    if not dest:
        raise ValueError("No backup folder set.")
    dest = _dest_ok(dest)
    if dest == Path(dest.anchor):
        raise ValueError("Pick a folder, not the root of a drive.")
    dest.mkdir(parents=True, exist_ok=True)
    now = (now or dt.datetime.now()).replace(microsecond=0)
    while (dest / ("jarvis-backup-" + now.strftime("%Y-%m-%d_%H%M%S"))).exists():
        now += dt.timedelta(seconds=1)               # two runs in the same second: next free name
    name = "jarvis-backup-" + now.strftime("%Y-%m-%d_%H%M%S")
    final, part = dest / name, dest / (name + ".partial")
    if part.exists():
        shutil.rmtree(str(part))
    part.mkdir()
    files = size = 0
    for d in DIRS:
        src = store.DATA_DIR / d
        if src.is_dir():
            shutil.copytree(str(src), str(part / d), ignore=shutil.ignore_patterns("__pycache__", "*.tmp"))
    if capture.SETTINGS.exists():
        shutil.copy2(str(capture.SETTINGS), str(part / "settings.json"))
    for p in part.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    (part / "manifest.json").write_text(json.dumps({
        "created": now.isoformat(timespec="seconds"), "source": str(store.DATA_DIR),
        "files": files, "bytes": size, "folders": [d for d in DIRS if (part / d).is_dir()]}, indent=1),
        encoding="utf-8")
    part.rename(final)
    # Prune: only folders this script made, newest KEEP kept.
    ours = sorted(p for p in dest.iterdir() if p.is_dir() and NAME_RE.match(p.name))
    removed = []
    for old in ours[:-KEEP]:
        shutil.rmtree(str(old))
        removed.append(old.name)
    s = capture.load_settings()
    s["backup_dest"] = str(dest)
    s["last_backup"] = now.isoformat(timespec="seconds")
    capture.save_settings(s)
    return {"path": str(final), "files": files, "bytes": size, "removed": removed, "kept": min(len(ours), KEEP)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sh jarvis.sh backup", description="Back up JARVIS bench data.")
    ap.add_argument("--dest", help="backup folder (remembered in jarvis/settings.json)")
    ap.add_argument("--status", action="store_true", help="show the saved folder and last backup, then exit")
    a = ap.parse_args(argv)
    st = status()
    if a.status:
        print("Backup folder: %s" % (st["dest"] or "(not set)"))
        print("Last backup:   %s" % ("never" if not st["last"] else "%s (%d days ago)" % (st["last"], st["age_days"])))
        return 0
    dest = a.dest or st["dest"]
    if not dest:
        if not sys.stdin.isatty():
            print("No backup folder set. Run: sh jarvis.sh backup --dest /path/to/folder")
            return 2
        print("Choose a backup folder once (for example a USB drive: /Volumes/BENCHUSB/jarvis).")
        print("Avoid synced cloud folders: the logs and settings are confidential.")
        dest = input("Backup folder: ").strip()
        if not dest:
            print("No folder given. Nothing backed up.")
            return 2
    try:
        r = run(dest)
    except (ValueError, OSError) as e:
        print("Backup failed: %s" % e)
        return 1
    print("Backed up %d files (%.1f MB) to %s" % (r["files"], r["bytes"] / 1e6, r["path"]))
    if r["removed"]:
        print("Removed %d old backup(s); keeping the newest %d." % (len(r["removed"]), KEEP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
