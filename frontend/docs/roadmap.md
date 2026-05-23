# Roadmap

## What's shipped

- **Core sync engine** — event-driven webhook pipeline, Hevy workout injected into Strava activity title and description
- **Automatic webhook registration** — registers with Strava on startup, no manual curl commands
- **OAuth flow** — full browser-based Strava authorization via `/auth/login`
- **Type isolation** — only `WeightTraining` and `Workout` activities are processed
- **Web configuration dashboard** — runtime settings management without container restarts
- **HTTP Basic Auth** — dashboard and config endpoints protected
- **Two Docker images** — standalone (`:latest`) and Caddy-bundled (`:caddy`) for auto-HTTPS

---

## What's coming

### Summary metrics in description
Calculate and display total sets, reps, and volume at the top of the workout description — pulled directly from Hevy's payload. Volume calculation will account for set types (working vs. warmup vs. dropset) and exercise types (bodyweight, weighted, etc.) to match Hevy's own numbers.

### Intensity-based muscle map
Dynamically generate a front/back anatomical muscle map image shaded by workout intensity and attach it to the Strava activity as a photo. Bypasses Strava's partner-only muscle map restrictions by generating and uploading our own image.

### Backfill past activities
A one-shot command or endpoint to retroactively sync historical Strava activities that predate Hevva's installation, with a configurable lookback window.

---

## Ideas and contributions

Have a feature idea, found a bug, or want to improve something?

[Open a GitHub issue](https://github.com/dharmendra-gupta/hevva/issues/new) — all feedback is welcome.

This project is open source under the [MIT License](https://github.com/dharmendra-gupta/hevva/blob/main/LICENSE).
