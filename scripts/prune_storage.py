"""Delete the large per-video files under data/videos and data/eval, keeping small JSON for research.

Dry run by default. Pass --apply to delete.
    python scripts/prune_storage.py [--apply] [--skip-eval] [--min-mb 5]
"""
import argparse
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
MEDIA = {".m4a", ".mp4", ".mp3", ".wav", ".webm", ".mkv"}
CHAT = {"chat.json", "yt_chat.live_chat.json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete (default is dry run)")
    ap.add_argument("--skip-eval", action="store_true", help="leave data/eval alone")
    ap.add_argument("--min-mb", type=float, default=5, help="chat logs below this size are kept")
    args = ap.parse_args()

    roots = [DATA / "videos"] + ([] if args.skip_eval else [DATA / "eval"])
    min_bytes = args.min_mb * 1024 * 1024
    total = count = 0
    for root in roots:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            size = f.stat().st_size
            if f.suffix.lower() in MEDIA or (f.name in CHAT and size >= min_bytes):
                print(f"{size / 1048576:8.1f} MB  {f.relative_to(DATA)}")
                total += size
                count += 1
                if args.apply:
                    f.unlink()
        if args.apply:
            # drop folders emptied by the delete, deepest first
            for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
                if not any(d.iterdir()):
                    d.rmdir()

    verb = "Deleted" if args.apply else "Would delete"
    print(f"\n{verb} {count} files, {total / 1048576:.0f} MB")
    if not args.apply:
        print("Dry run. Re-run with --apply to delete.")


if __name__ == "__main__":
    main()
