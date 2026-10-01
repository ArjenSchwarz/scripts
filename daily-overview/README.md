# Daily overview renderer

Offline, code-rendered **TEST PREVIEW** for 2 October 2026. No actual commitments are asserted. The original export is untouched. `sample-input.json` is its exact copy; `work-feed.json` is the captured categories-only partial work feed from https://ig.nore.me/day-shape/tomorrow.json. Work feed snapshot: 1 October 18:10 Melbourne; Personal/Family snapshot: 1 October 23:35 Melbourne. The script never downloads feeds automatically.

## Run

Python 3.9+ with an IANA timezone database (standard on macOS/Linux), Pillow 11.3.0, and the included Lato fonts. On systems without timezone data, install `tzdata` in the virtual environment. No privileged installation needed.

```sh
cd /Users/arjen/Documents/Codex/2026-10-01/task-2/daily-overview
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python render.py sample-input.json --work work-feed.json --output overview.png
.venv/bin/python -m unittest discover -s . -v
```

After extracting the ZIP elsewhere, change `cd` to the extracted `daily-overview` folder. Omit `--work` for a Personal/Family-only view. Supply a new JSON export as the first argument to render another date. The script always labels output as test preview; it is intentionally unsuitable for presenting real commitments without adapting that label.

## Input and behavior

- Wrapper: `targetDate`, `generatedAt`, `generatedAtTimezone`, `calendarsIncluded`, `events`.
- Event: `title`, boolean `all_day`, `start_date`, `end_date`, `calendar_name`, IANA `timezone`.
- Offsetless datetimes use their named zone. Explicit offsets take precedence. Everything displays in Australia/Melbourne; Australia/Sydney agrees for this sample.
- All-day dates are floating calendar dates; **date-only end is inclusive**. They appear in a separate context strip, never in the timed-gap calculation.
- Timed intervals have exclusive ends, are clipped to the target day, and extend the timeline outside 09:00–17:30 when necessary. Cross-midnight cards identify that only the day's portion is shown. `24:00` is the visual label for the following midnight.
- Overlaps use separate narrow timeline lanes; cards stack with leader lines to exact-duration bars, preserving readable labels for short events. Titles wrap rather than truncate. Work, Personal and Family each have consistent colors plus text labels.
- Gap calculation unions all supplied timed blocks inside **09:00–17:30**. It deliberately recomputes gaps after combining sources, rather than trusting the work feed's `free_windows`. Optional and unresolved work blocks conservatively count as supplied blocks.
- All focus windows say **partial coverage; availability is not guaranteed**. Unknown/missing calendars, excluded recurring events, RSVP changes, and all-day context may still affect availability.
- Calendar names containing Work/Personal/Family select that style; other calendars use the Personal style. Exact included names appear in the coverage footer.
- Source timestamps are shown separately in Melbourne time. Snapshots older than 24 hours at target-day midnight receive a freshness flag. The renderer never uses the wall clock, so output is reproducible from captured input.
- Invalid durations, mismatched feed dates, unknown work categories, invalid zones, sub-minute precision, ambiguous or nonexistent local times are rejected. **DST transition target days are explicitly rejected**, rather than misrepresenting a 23/25-hour day. Normalize nonempty work-feed `all_day` data into the event schema; unsupported nonempty work all-day data is rejected.
- Same bytes are produced with the same inputs, included fonts, Pillow build and timezone database. Different dependency or timezone-database versions are outside that guarantee.

## Validation

Seven unittest cases cover the three expected gaps (09:00–10:00, 12:00–15:00, 15:25–17:30), PNG integrity, identical SHA-256 across two renders, overlap union, empty/all-day-only days, inclusive all-day end, long titles, midnight clipping, named-zone/UTC equivalence, DST/invalid rejection. The final PNG was opened and visually inspected: all titles, exact 15:00–15:25 label, all-day strip, test label, coverage qualifier and both source timestamps are readable. `overview.png` is 1080 × 1968. A text summary can be obtained from the script's JSON stdout; PNG itself is not a screen-reader document.

The bundle includes Lato fonts under their SIL Open Font License (`OFL.txt`). Arial system fonts are not distributed. No repositories or automations were changed.
