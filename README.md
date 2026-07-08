# Virtracker · SEO Monitor

A friendly, self-contained dashboard for the daily SEO tracking data in the
["SEO Rapporting" Google Sheet](https://docs.google.com/spreadsheets/d/1lTLFb-eC4ElEpzX684X-XQvJTNBPR7Jv0D1WGKnqH7E/edit?gid=380445228)
(Snapshots tab).

## Viewing

Open `index.html` in any browser — no server, no build step, no dependencies.
The data is embedded in the file, so it also works offline and can be hosted
anywhere (GitHub Pages works out of the box). Light and dark mode both
supported.

What you get:

- **KPI tiles** — flags today, striking-distance pages, high/critical flags, new wins
- **Flags per day** — trend line over the whole tracking period
- **What kind of flags?** — daily breakdown by flag type (new pages, position decay, striking distance, …)
- **Striking-distance opportunities** — pages at position 8–20 that are almost on page 1
- **Needs attention** — high-severity flags from the latest scan
- **Recent wins** — click surges and new pages that are earning clicks
- Filters for **period** (14/30/all days) and **site** — every chart, number and table re-scopes together

## Refreshing the data

1. Open the sheet, go to the **Snapshots** tab
2. File → Download → **Comma Separated Values (.csv)**
3. Run:

```sh
python3 scripts/refresh_data.py ~/Downloads/snapshots.csv
```

That re-aggregates everything and re-embeds it into `index.html`. Commit and
push to publish.
