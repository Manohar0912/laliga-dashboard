# LaLiga Analytics Dashboard

Historical and current-season LaLiga analytics dashboard covering the competition from **1928/29 onward**.

This repository is being set up with:

- all-time LaLiga match history
- current-season fixtures and results refresh
- team intelligence and season match-centre analytics
- all-time H2H analysis
- match predictions
- nightly validation, model retraining and rebuild through GitHub Actions
- GitHub Pages deployment

The automated refresh runs nightly to capture completed results, retrain predictions, validate the build and redeploy the dashboard. A manual workflow trigger remains available for on-demand updates.
