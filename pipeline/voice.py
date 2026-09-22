"""Step 3: Vietnamese speech with edge-tts, one mp3 for the day.

edge-tts is Microsoft's free voice. No key, no daily limit. Microsoft does not
promise it to us, so it can break without warning; when it does, the log must
say why in one clear line. This file is DeViDa's voice.py with small changes.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

PCM_RATE = 24000
PCM_WIDTH = 2
TRIES = 6
# Each try waits longer than the last. Microsoft answers "no audio received"
# when it is busy, and asking again a few seconds later gets the same answer.
# On 2026-09-22 the same paragraph failed three times in a row and then worked.
RETRY_WAITS = (10, 30, 60, 120, 240)
# A short breath between pieces, so we do not hit Microsoft in a burst.
BETWEEN_PIECES = 1.0


class VoiceError(RuntimeError):
    pass


class BadCommand(VoiceError):
    """Our own command line is wrong. Trying again would fail the same way."""


def _edge_binary() -> str:
    beside_python = Path(sys.executable).parent / "edge-tts"
    return str(beside_python) if beside_python.exists() else "edge-tts"


def _edge_reason(stderr: str) -> str:
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    return lines[-1][:300] if lines else "no error message"


def _is_bad_command(stderr: str) -> bool:
    text = (stderr or "").lower()
    return "error: argument" in text or "error: unrecognized arguments" in text


def _speak_once(text: str, voice: str, rate: str, target: Path) -> None:
    command = [_edge_binary(), "--voice", voice, "--text", text, "--write-media", str(target)]
    if rate and rate != "+0%":
        command.append(f"--rate={rate}")  # one word with "=", or "-10%" looks like an option
    done = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if done.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        reason = _edge_reason(done.stderr)
        if _is_bad_command(done.stderr):
            raise BadCommand(f"edge-tts refused our command: {reason}")
        raise VoiceError(f"edge-tts failed: {reason}")


def speak_piece(text: str, voice: str, rate: str, target: Path) -> None:
    last: VoiceError | None = None
    for attempt in range(1, TRIES + 1):
        try:
            _speak_once(text, voice, rate, target)
            return
        except BadCommand:
            raise
        except (VoiceError, subprocess.TimeoutExpired) as err:
            last = err if isinstance(err, VoiceError) else VoiceError(f"edge-tts timed out: {err}")
            log.warning("voice: try %d of %d failed (%s)", attempt, TRIES, last)
            if attempt < TRIES:
                wait = RETRY_WAITS[min(attempt - 1, len(RETRY_WAITS) - 1)]
                log.info("voice: waiting %ds before trying again", wait)
                time.sleep(wait)
    raise last or VoiceError("edge-tts failed for an unknown reason")


def fingerprint(parts: list[str]) -> str:
    """Names exactly what a sound file says, so the page never plays a sound
    that does not match the words next to it."""
    digest = hashlib.sha1()
    digest.update(f"{len(parts)}\x00".encode("utf-8"))
    for part in parts:
        raw = part.encode("utf-8")
        digest.update(f"{len(raw)}\x00".encode("utf-8"))
        digest.update(raw)
    return digest.hexdigest()


def stamp_file(workdir: Path) -> Path:
    return workdir / "audio.sha1"


def audio_matches(workdir: Path, parts: list[str]) -> bool:
    saved = stamp_file(workdir)
    mp3 = workdir / "audio.mp3"
    if not saved.is_file() or not mp3.is_file() or mp3.stat().st_size == 0:
        return False
    return saved.read_text(encoding="utf-8").strip() == fingerprint(parts)


def _to_pcm(source: Path) -> bytes:
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-"],
        capture_output=True, timeout=600,
    )
    if done.returncode != 0:
        raise VoiceError(f"ffmpeg decode failed: {done.stderr.decode()[:300]}")
    return done.stdout


def silence(seconds: float) -> bytes:
    return b"\x00" * (int(PCM_RATE * seconds) * PCM_WIDTH)


def speak_day(pieces: list[str], workdir: Path, voice: str, rate: str, pause_seconds: float) -> Path:
    """One mp3 for the whole day. Each piece (a section) is spoken once and
    cached, so a retry resumes where it stopped."""
    if not pieces:
        raise VoiceError("nothing to speak")
    cache = workdir / "tts"
    cache.mkdir(parents=True, exist_ok=True)
    raw = workdir / "day.pcm"
    reused = 0
    with raw.open("wb") as sink:
        for number, text in enumerate(pieces, start=1):
            digest = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:10]
            piece_mp3 = cache / f"{number:03d}-{digest}.mp3"
            if piece_mp3.is_file() and piece_mp3.stat().st_size > 0:
                reused += 1
            else:
                speak_piece(text, voice, rate, piece_mp3)
                log.info("voice %d/%d: %d bytes", number, len(pieces), piece_mp3.stat().st_size)
                time.sleep(BETWEEN_PIECES)
            sink.write(_to_pcm(piece_mp3))
            if number < len(pieces):
                sink.write(silence(pause_seconds))
    if reused:
        log.info("voice: reused %d pieces from an earlier run", reused)
    mp3 = workdir / "audio.mp3"
    encode_mp3(raw, mp3)
    raw.unlink(missing_ok=True)
    stamp_file(workdir).write_text(fingerprint(pieces), encoding="utf-8")
    return mp3


def encode_mp3(pcm: Path, mp3: Path) -> None:
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", str(pcm),
         "-codec:a", "libmp3lame", "-b:a", "64k", "-ac", "1", str(mp3)],
        capture_output=True, timeout=900,
    )
    if done.returncode != 0:
        raise VoiceError(f"ffmpeg encode failed: {done.stderr.decode()[:400]}")


def duration_seconds(mp3: Path) -> int:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return int(float(done.stdout.strip()))
    except ValueError:
        return 0


def clean_for_speech(text: str) -> str:
    """Small fixes so Microsoft does not choke: no '…' (it made a whole piece
    fail on 2026-09-22), no control characters, single spaces."""
    text = text.replace("\u2026", "...").replace("\xa0", " ")
    text = "".join(c for c in text if c >= " " or c in "\n\t")
    return " ".join(text.split())


def spoken_pieces(sections: list[dict]) -> list[str]:
    """One piece per paragraph, with the section title as its own piece first.
    Short pieces fail less often than long ones, and a failed piece is retried
    alone instead of speaking the whole section again."""
    out: list[str] = []
    for s in sections:
        title = clean_for_speech(s["title"])
        if title:
            out.append(title if title.endswith((".", "!", "?")) else title + ".")
        for p in s["paragraphs"]:
            p = clean_for_speech(p)
            if p:
                out.append(p)
    return out
