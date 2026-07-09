# Virtracker · SEO Monitor

A friendly, self-contained dashboard for the daily SEO tracking data in the
["SEO Rapporting" Google Sheet](https://docs.google.com/spreadsheets/d/1lTLFb-eC4ElEpzX684X-XQvJTNBPR7Jv0D1WGKnqH7E/edit?gid=380445228)
(Snapshots tab).

## Viewing

Open `index.html` in any browser — no server, no build step, no dependencies.
The data is embedded in the file, so it also works offline and can be hosted
anywhere (GitHub Pages works out of the box). Light and dark mode both
supported.

What you get — a dashboard app with a collapsible sidebar (Home, Traffic,
Flags, Opportunities, Needs attention, Wins) in shadcn-style design with
lucide icons, light & dark mode:

- **Home** — a hero that names the **top 3 highest-impact moves for today**
  (best striking-distance push, worst regression to rescue, biggest CTR fix)
- **Traffic** — clicks & impressions KPIs, a trend chart with a
  Clicks/Impressions toggle, and a **Main pages** overview: your busiest pages
  with a per-page trend sparkline, 7-day click delta, CTR and position
- **Flags** — flags per day, breakdown by flag type, and flags by site
- **Opportunities** — pages at position 8–20 that are almost on page 1
- **Needs attention** — high-severity flags from the latest scan
- **Wins** — click surges and new pages that are earning clicks
- **KPI tiles are clickable** — each one opens its section; the sidebar shows
  live counts as badges
- **＋ New project** (bottom left) — opens the n8n project form in a modal
- Filters for **period** (14/30/all days) and **site** — everything re-scopes together

## Exporting (great for AI)

- **Copy AI brief** (top right) — copies a Markdown summary of everything on
  screen (headline numbers, main pages, opportunities, needs-attention, wins,
  full URLs included). Paste it straight into an AI chat and ask for an action plan.
- **Report .md** — downloads the same brief plus the daily traffic table.
- **Data .csv** — downloads the latest scan's flags as CSV.
- **Print / PDF** — clean print stylesheet for a shareable PDF.
- Every table card has its own **Copy** button; *Needs attention* also has a
  one-click **.csv** download.
- Programmatic: `window.virtracker.aiBrief()` / `.fullReport()` / `.csv()` in
  the browser console (or via headless automation).

All exports respect the period/site filters you have selected.

## Refreshing the data

### Option A — Google service account (no manual download)

One-time setup:

1. In [Google Cloud Console](https://console.cloud.google.com/), create (or
   reuse) a project → enable the **Google Sheets API**.
2. Create a **service account** (IAM & Admin → Service accounts) and download
   a **JSON key**.
3. Share the SEO Rapporting sheet with the service account's
   `...@...iam.gserviceaccount.com` email (Viewer is enough).

Then refresh with:

```sh
python3 scripts/refresh_data.py --service-account path/to/key.json
```

No Python packages needed — only the `openssl` command, which macOS and Linux
ship with. Optional flags: `--sheet-id`, `--tab` (default `Snapshots`),
`--save-csv backup.csv`.

⚠️ Keep the key file out of the repo (don't commit it).

### Option B — CSV export

1. Open the sheet, go to the **Snapshots** tab
2. File → Download → **Comma Separated Values (.csv)**
3. Run:

```sh
python3 scripts/refresh_data.py ~/Downloads/snapshots.csv
```

Either way the script re-aggregates everything (including per-page traffic)
and re-embeds it into `index.html`. Commit and push to publish.
