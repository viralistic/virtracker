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
- **Traffic** — a **day / week / all-time summary** (clicks & impressions for
  the latest day, this week vs last week, and all-time totals), clicks &
  impressions KPIs, a trend chart with a Clicks/Impressions toggle, and a
  **Main pages** overview: your busiest pages with a per-page trend sparkline,
  7-day click delta, CTR and position
- **Flags** — flags per day, breakdown by flag type, and flags by site
- **Opportunities** — pages at position 8–20 that are almost on page 1
- **Needs attention** — high-severity flags from the latest scan
- **Wins** — click surges and new pages that are earning clicks
- **KPI tiles are clickable** — each one opens its section; the sidebar shows
  live counts as badges. Tiles turn green when performing, red when action is needed
- **Clients live in the sidebar** — pick a client (or All projects) and every
  number, chart, table and export re-scopes to it
- **＋ New project** (bottom left) — opens the n8n project form in a modal
- A **period** filter (14/30/all days) in the top bar

## Client-facing PDF report

The **PDF** button prints a dark `#0A0A0B` (edge to edge), Viralistic-branded
report: your **actual Performance Raport cover** as page 1 (with the client
name + period overlaid), headline tiles, the top-3 priorities, a **performance
page** (clicks graph + impressions graph over the full period, plus a weekly
breakdown table), day/week/all-time summary, main pages, opportunities, wins,
a glossary that explains CTR/position/etc., and your **actual "Any Questions?"
closing page** last. It contains **only the selected client's data** (the
cross-site comparison only appears on All projects).

The two cover pages are the brand PDFs embedded as images. To swap them for
updated versions:

```sh
pdftoppm -jpeg -r 150 -f 1 -l 1 "Front page SEO Rapport.pdf" front
pdftoppm -jpeg -r 150 -f 1 -l 1 "Closing Page SEO rapport.pdf" closing
python3 scripts/embed_report_art.py front-1.jpg closing-1.jpg
```

Print tips: in the print dialog, turn **off** "Headers and footers" and leave
**Background graphics on** (that's what fills the page with the dark color).

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
