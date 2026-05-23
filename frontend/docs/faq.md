# FAQ

### Does Hevva run background jobs or poll APIs constantly?

No. Hevva is purely reactive and event-driven. It spends virtually all of its time idle, consuming no CPU. It only executes for a few seconds when Strava's webhook explicitly wakes it up with a new activity event.

---

### Why doesn't Hevva use Strava's native workout log blocks?

Strava restricts native workout log arrays and muscle maps to their proprietary upload flow. Using that flow forces you to discard your wearable sensor data — heart rate graphs, recovery timelines, and calorie estimates. Hevva uses the standard `PUT /activities/{id}` endpoint instead, keeping all your biometric data intact while injecting the Hevy exercise log into the description.

---

### What happens if I record a run or a bike ride?

Hevva includes a strict type filter. If the incoming webhook event is for a sport type other than `WeightTraining` or `Workout`, Hevva logs it as dropped and stops processing immediately. Your runs and rides are never touched.

---

### What if I don't sync my watch right away?

Not a problem. Hevva matches workouts using the timestamps embedded in the saved data — not the time the sync runs. Even if you sync your watch hours after finishing your session, the time-delta matching will find the correct Hevy workout as long as it falls within the configured sync window.

---

### I see duplicate activities on Strava — is that Hevva?

No. Hevva only updates existing activities — it never creates new ones. Duplicates come from two sources pushing to Strava independently: your wearable (Garmin, Polar, etc.) and Hevy's own native Strava sync. To fix this, disable Hevy's Strava integration in **Hevy → Settings → Connected Apps**. See the [setup guide](setup.md#step-6-disable-hevys-native-strava-sync) for details.

---

### Can I change the sync window without restarting the container?

Yes. Use the web dashboard at `https://hevva.yourdomain.com/` to update the sync window. Changes take effect on the next webhook event — no restart needed.

---

### Where are tokens and settings stored?

In `./data/Hevva.db` — a SQLite file in the mounted data volume. Strava OAuth tokens are stored there and refreshed automatically before every API call. You only need to re-authorize if you explicitly revoke access on Strava.

---

### Does this work with Apple Watch?

Apple Watch users typically have native integrations (Apple Health, etc.) that handle Strava sync differently. Hevva is designed for athletes using a dedicated sports wearable (Garmin, Polar, Coros, Whoop) alongside Hevy.
