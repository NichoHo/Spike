"""
Spike: Command-Line Interface
Blueprint §13 Phase 1:
- spike run <file-or-url>
- spike eval <dataset.json>
- spike status <video_id>
"""

import sys
import argparse
import subprocess
import threading
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.runner import run_pipeline
from src.eval import run_evaluation
from src.db import get_connection


def cmd_run(args):
    """Run full pipeline on a video file or URL."""
    source_input = args.input
    run_pipeline(source_input)


def cmd_eval(args):
    """Evaluate detected moments against ground truth dataset."""
    run_evaluation(args.dataset)


def cmd_status(args):
    """Check pipeline status for a video in the database."""
    video_id = args.video_id
    with get_connection() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            print(f"Error: Video ID {video_id} not found in database.")
            return

        print(f"\n--- Video {video_id} Status ---")
        print(f"Title:    {video['title']}")
        print(f"Origin:   {video['origin']}")
        print(f"Status:   {video['status']}")
        print(f"Stage:    {video['stage']}")
        if video['error']:
            print(f"Error:    {video['error']}")

        cands = conn.execute(
            "SELECT id, final_score, title, punchline, start_s, end_s FROM candidates WHERE video_id = ? ORDER BY final_score DESC",
            (video_id,)
        ).fetchall()
        print(f"\nCandidates ({len(cands)} total):")
        for c in cands:
            dur = c['end_s'] - c['start_s']
            print(f"  [{c["llm_score"]}/100] {c['title']} ({dur:.1f}s) -> \"{c['punchline']}\"")


def cmd_watch(args):
    """Run source watcher daemon to check for new VODs and uploads."""
    from src.watcher import run_watcher_loop
    run_watcher_loop(single_run=args.once)


def cmd_web(args):
    """Start the FastAPI web application."""
    import uvicorn
    from src.config import WEB_HOST, WEB_PORT
    host = args.host or WEB_HOST
    port = args.port or WEB_PORT
    print(f"Starting Spike Web App on http://{host}:{port} ...")

    # Worker and watcher run as child processes. A daemon thread restarts any that die.
    # ponytail: a hard kill of this process (taskkill /F) orphans the children; use a Windows Job object if that bites.
    cmds = []
    if not args.no_worker:
        cmds.append([sys.executable, sys.argv[0], "worker"])
    if not args.no_watcher:
        cmds.append([sys.executable, sys.argv[0], "watch"])
    if not args.no_outreach:
        cmds.append([sys.executable, sys.argv[0], "outreach"])
    children = [subprocess.Popen(c) for c in cmds]

    def supervise():
        while True:
            time.sleep(30)
            for i, p in enumerate(children):
                # 0 = clean exit, 0xC000013A = killed by Ctrl+C. Both mean "shutting down", not a crash.
                if p.poll() is not None and p.returncode not in (0, 3221225786):
                    print(f"[web] '{cmds[i][-1]}' exited with code {p.returncode}; restarting.")
                    children[i] = subprocess.Popen(cmds[i])

    threading.Thread(target=supervise, daemon=True).start()
    try:
        uvicorn.run("src.web.app:app", host=host, port=port, reload=args.reload, timeout_graceful_shutdown=3)
    finally:
        for p in children:
            p.terminate()


def cmd_evalset(args):
    """Per-category eval set: build labels, run Spike with clips held out, score against baselines."""
    from src import eval_set
    if args.action == "build":
        eval_set.build()
    elif args.action == "run":
        eval_set.run(args.vod)
    else:
        eval_set.print_report(eval_set.score())


def cmd_worker(args):
    """Start background worker daemon."""
    from src.worker import start_worker
    start_worker(poll_interval_s=args.interval)


def cmd_outreach(args):
    """Run the Outreach process: finder schedule, trial clips, drafts, sending, follow-ups (OUTREACH.md §6)."""
    if args.find_now:
        from src.outreach.daemon import run_finder_now
        from src.outreach.db import get_settings
        run_finder_now(get_settings())
        return
    from src.outreach.daemon import run_daemon
    run_daemon()


def cmd_music(args):
    """Validate music library licenses and list all tracks by mood."""
    from src.music import validate_music_library, list_all_tracks, MusicLicenseError
    try:
        res = validate_music_library(enforce=True)
        print("Music library license check: PASSED (all tracks have valid sidecars)\n")
        tracks = list_all_tracks()
        print(f"Available tracks ({len(tracks)} total):")
        for t in tracks:
            print(f"  [{t['mood'].upper()}] {t['title']} - {t['license']} ({t['rel_path']})")
    except MusicLicenseError as e:
        print(f"Music library check FAILED:\n{e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Spike: AI Short-Form Video Clip Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Process a video file or URL through the pipeline")
    run_parser.add_argument("input", help="Path to local video file or YouTube/Twitch URL")
    run_parser.add_argument("--chat", dest="chat_file", help="Optional local chat replay JSON file")
    run_parser.set_defaults(func=cmd_run)

    # eval command
    eval_parser = subparsers.add_parser("eval", help="Evaluate detection against ground truth dataset")
    eval_parser.add_argument("dataset", help="Path to JSON dataset with ground truth moments")
    eval_parser.set_defaults(func=cmd_eval)

    # status command
    status_parser = subparsers.add_parser("status", help="Show processing status of a video ID")
    status_parser.add_argument("video_id", type=int, help="Video ID in the database")
    status_parser.set_defaults(func=cmd_status)

    # watch command (§5, §13 Phase 3)
    watch_parser = subparsers.add_parser("watch", help="Run watcher daemon polling followed sources")
    watch_parser.add_argument("--once", action="store_true", help="Check sources once and exit")
    watch_parser.set_defaults(func=cmd_watch)

    # web command (§13 Phase 4)
    web_parser = subparsers.add_parser("web", help="Start FastAPI web server")
    web_parser.add_argument("--host", default=None, help="Host interface to bind to")
    web_parser.add_argument("--port", type=int, default=None, help="Port to bind to")
    web_parser.add_argument("--reload", action="store_true", help="Enable dev auto-reloading")
    web_parser.add_argument("--no-worker", action="store_true", help="Do not start the background worker")
    web_parser.add_argument("--no-watcher", action="store_true", help="Do not start the source watcher")
    web_parser.add_argument("--no-outreach", action="store_true", help="Do not start the outreach process")
    web_parser.set_defaults(func=cmd_web)

    # worker command (§13 Phase 4)
    worker_parser = subparsers.add_parser("worker", help="Start background queue worker")
    worker_parser.add_argument("--interval", type=float, default=5.0, help="Poll interval in seconds")
    worker_parser.set_defaults(func=cmd_worker)

    # outreach command (OUTREACH.md §6)
    outreach_parser = subparsers.add_parser("outreach", help="Run the outreach process (lead finder, trial clips, emails)")
    outreach_parser.add_argument("--find-now", action="store_true", help="Run the lead finder once and exit")
    outreach_parser.set_defaults(func=cmd_outreach)

    evalset_parser = subparsers.add_parser("evalset", help="Per-category eval set: build, run or score")
    evalset_parser.add_argument("action", choices=["build", "run", "score"])
    evalset_parser.add_argument("--vod", help="run only this VOD id")
    evalset_parser.set_defaults(func=cmd_evalset)

    # music command (§13 Phase 5)
    music_parser = subparsers.add_parser("music", help="Verify music library licenses and list tracks")
    music_parser.set_defaults(func=cmd_music)

    args = parser.parse_args()
    if hasattr(args, "chat_file") and args.chat_file:
        run_pipeline(args.input, source_settings={"chat_file": args.chat_file})
    else:
        args.func(args)


if __name__ == "__main__":
    main()

