# AGENTS.md

This repository is the **map-shorts** Agent Skill: vertical (1080x1920) map Shorts in which countries or historical
states rise from a NASA satellite map as flag-printed slabs while the camera flies between them. Two formats: a
ranking countdown ("largest countries in Africa, top 5") and a timeline ("how the EU grew"). One video is one
`show.json`.

When a user asks for a map Short, a country/area ranking video, or a map timeline of a country or empire:

1. Read [SKILL.md](SKILL.md) and follow its procedure: entries and sourced numbers, territories, `show.json`,
   `--plan`, stills you open and look at, the full render in the background, delivery. It is written in Korean;
   answer the user in their language.
2. Run everything through `scripts/run.py` (needs only Python 3.10+; the first run installs the packages and an
   ffmpeg into `~/.cache/map-shorts/venv`):
   ```bash
   python3 scripts/run.py countries france vietnam
   python3 scripts/run.py episodes/<slug> --plan
   python3 scripts/run.py episodes/<slug> --still 4.6,7.9
   python3 scripts/run.py episodes/<slug> --fps 30 > episodes/<slug>/out/render.log 2>&1 &
   python3 scripts/run.py episodes/<slug> --status
   ```
3. The `show.json` format is in [references/show-json.md](references/show-json.md); examples are in
   `assets/examples/` (a ranking and a timeline).
4. Map data, borders, flags and fonts download on first use to `~/.cache/map-shorts` (or `$MAP_SHORTS_DATA`). The
   first still of a new region can take several minutes, so give that command a long timeout.
5. Deliver `episodes/<slug>/out/video.mp4` and say where the numbers came from and which borders are approximate.

To install the skill for your agent instead of working inside this folder, run `./install.sh` (see README.md).
