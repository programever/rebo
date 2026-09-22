"""One run: plan today's reading, make the sound, publish the page.

    python -m pipeline.main                 today, all steps
    python -m pipeline.main --dry-run       everything, but nothing is pushed
    python -m pipeline.main --skip-voice    plan and page only; no sound, no push
    python -m pipeline.main --publish-only  rebuild the page from the days on this box
    python -m pipeline.main --force         plan today again from the same place
    python -m pipeline.main --date 2026-09-22
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from . import plan, publish, voice
from .config import OUT_DIR, Config, day_dir, today_vietnam

log = logging.getLogger("rebo")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build today's reading and publish it.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-voice", action="store_true")
    ap.add_argument("--publish-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    cfg = Config.load()
    day = args.date or today_vietnam()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = OUT_DIR / "last-run.txt"

    try:
        if not args.publish_only:
            if args.force:
                plan.undo_day(day)
            reading = plan.plan_day(day, cfg.words_per_day)
            folder = day_dir(day)
            pieces = voice.spoken_pieces(reading.sections)
            if args.skip_voice:
                log.info("voice: skipped")
            elif voice.audio_matches(folder, pieces):
                log.info("voice: today's sound already exists and matches the words")
            else:
                try:
                    mp3 = voice.speak_day(pieces, folder, cfg.tts_voice, cfg.tts_rate, cfg.pause_seconds)
                    log.info("voice: %s, %d seconds", mp3.name, voice.duration_seconds(mp3))
                except voice.VoiceError as err:
                    # The day is still published, just without sound.
                    log.error("voice failed, publishing without sound: %s", err)
                    voice.stamp_file(folder).unlink(missing_ok=True)
        url, days = publish.publish(cfg, dry_run=args.dry_run or args.skip_voice)
        line = f"{day.isoformat()} ok: {url} ({len(days)} days)"
        summary.write_text(line + "\n", encoding="utf-8")
        log.info(line)
        return 0
    except Exception as err:  # noqa: BLE001 - the last line of the log must say what went wrong
        line = f"{day.isoformat()} FAILED: {type(err).__name__}: {err}"
        summary.write_text(line + "\n", encoding="utf-8")
        log.error(line)
        return 1


if __name__ == "__main__":
    sys.exit(main())
