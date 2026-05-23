import os

os.environ.setdefault("STRAVA_CLIENT_ID", "test_client_id")
os.environ.setdefault("STRAVA_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("STRAVA_VERIFY_TOKEN", "test_verify_token")
os.environ.setdefault("HEVY_API_KEY", "test_hevy_key")
os.environ.setdefault("WEBHOOK_CALLBACK_URL", "https://hevva.example.com/webhook")
os.environ.setdefault("STRAVA_REDIRECT_URI", "http://localhost:8888/callback")
os.environ.setdefault("DASHBOARD_USERNAME", "admin")
os.environ.setdefault("DASHBOARD_PASSWORD", "changeme")
