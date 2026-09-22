# Rebo

Rebo reads a book to you, one passage a day.

Every morning it takes the next few sections of a book by Thích Nhất Hạnh,
makes a Vietnamese voice reading of them, and publishes a page with the text
and the sound. The books come from the free library of Làng Mai:
https://langmai.org/tang-kinh-cac/vien-sach/thien-tap/ (Iker checked the
licence with them, 2026-09-22). Every page links back to that library.

The page: https://programever.github.io/rebo/

## What one day is

- A day is a few sections in a row, about 2,000 words or a little more.
  A section is never cut in the middle. That is 12 to 15 minutes of listening.
- When a part (chapter) ends, the next part starts the next day.
- When a book ends, the next book in `books.txt` starts. When that list is used
  up, the next book in the library follows.
- If a day is missed (box off, site down), nothing is skipped. The next run
  simply continues from the same place.
- The page shows the last 10 days. Older days stay on this box in `out/days/`
  for ever; they only stop being published.

## How a run works

1. **Plan.** Read `out/progress.json` (which book, which part, which section
   is next). Fetch the part page from langmai.org, split it into sections, take
   sections until the word budget is full. Save `out/days/<date>/reading.json`
   and move the progress on. A day that was already planned is reused.
2. **Voice.** Microsoft's free voice (edge-tts, `vi-VN-HoaiMyNeural`). One
   call per paragraph, joined into one mp3 with short pauses. A failed call is
   tried again, waiting longer each time. If the voice fails completely, the
   day is still published, just without sound.
3. **Page.** Plain HTML, no JavaScript. The front page shows today in full and
   lists the earlier days. Each day has its own page and its own sound file.
4. **Publish.** The `gh-pages` branch is rebuilt from nothing and force-pushed,
   so it always holds one commit and only the days on the page. The repo can
   never grow. This is the same rule as DeViDa (Iker, 2026-09-16).

The `main` branch holds the code and is kept as one squashed commit (Iker's
wish for these small projects).

## Files

| File | What it is |
|---|---|
| `pipeline/config.py` | Settings: repo, page address, voice, words per day, days on the page. |
| `pipeline/fetch.py` | Reads the library, a book's parts, and a part's sections from langmai.org. Pages are cached in `out/cache/`. |
| `pipeline/plan.py` | Decides today's reading and moves the progress on. |
| `pipeline/voice.py` | Makes the sound with edge-tts and ffmpeg. |
| `pipeline/site.py` | Writes the HTML pages. |
| `pipeline/publish.py` | Force-pushes the page branch, with guards. |
| `pipeline/main.py` | One run, all steps. |
| `books.txt` | The books to read, in order. |
| `selftest.py` | Tests with saved pages, no internet needed. Run before every push. |
| `run.sh` | The command the timer runs. |
| `rebo.service`, `rebo.timer` | The daily run at 03:30 Vietnam time, retries at 04:30 and 06:00 (they only add missing sound). |

## Commands

```
./setup.sh                 # once: make the Python environment
.venv/bin/python selftest.py
./run.sh                   # today, all steps, publish
./run.sh --dry-run         # everything, but nothing is pushed
./run.sh --skip-voice      # text and page only, no sound, no push
./run.sh --publish-only    # rebuild the page from the days on this box
./run.sh --force           # plan today again from the same place
./run.sh --date 2026-09-22
```

Install the timer:

```
cp rebo.service rebo.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rebo.timer
```

Check the last run: `cat out/last-run.txt` or `journalctl --user -u rebo.service -n 50`.

## To change the book order

Edit `books.txt`. The name of a book is the last part of its address on
langmai.org, for example `phep-la-cua-su-tinh-thuc`. To jump to another
place, edit `out/progress.json` and run `./run.sh --force`.

## To remove Rebo

```
systemctl --user disable --now rebo.timer
rm ~/.config/systemd/user/rebo.service ~/.config/systemd/user/rebo.timer
systemctl --user daemon-reload
rm -rf ~/rebo
```

Then delete the `Rebo` repo on GitHub, or leave it: the page stays as it is.
