# Football Intelligence — Unified Dashboard

This branch contains the unified multi-competition dashboard.

## Data source

The Big Five leagues use public OpenFootball / football.json files hosted on GitHub:

- Premier League
- LaLiga
- Bundesliga
- Serie A
- Ligue 1

No API key is required, and the dashboard does not use the API-Sports 100-requests-per-day quota.

The following competitions are already present in the navigation but currently show **Source pending** until a reliable open current-season source is added:

- UEFA Champions League
- UEFA Europa League
- UEFA Conference League
- Copa del Rey
- Carabao Cup / EFL Cup
- FA Cup

## GitHub Pages

This dashboard is static, so it can be hosted directly with GitHub Pages.

To publish this branch:

1. Open the repository **Settings**.
2. Open **Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Select branch **unified-football-dashboard**.
5. Select **/(root)**.
6. Save.

The site will then be available on the repository's GitHub Pages URL.

## Notes

OpenFootball is community-maintained and is not a live-score service. Tables and league statistics are calculated in the browser from the published fixture/result files.
