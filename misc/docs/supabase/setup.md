# Supabase storage and Google accounts

The app stores prospects, transcripts, settings, and call metrics in Supabase. You sign in with Google in the browser. Each Gmail account only sees its own data. Supabase URL and keys stay in the private `.env` file on the machine that runs `server.py` — they are not entered in Settings.

If Supabase is not configured, the app uses the local `crm_data` folder and `metrics.json` and does not show Google sign-in.

## Configure

1. Create a Supabase project.
2. In the SQL editor, run [`schema.sql`](./schema.sql). Re-run it on existing projects to add `user_id` columns and Google-account policies.
3. Add these to the private `.env` file (see [`.env.example`](../../.env.example)):
   - `SUPABASE_URL`: `https://your-project.supabase.co`
   - `SUPABASE_SECRET_KEY`: server secret (`sb_secret_...`) or legacy `service_role` JWT
   - `SUPABASE_ANON_KEY`: the project's anon/publishable key (safe to send to the browser for Auth only)
4. In Supabase: **Authentication → Providers → Google**. Turn it on and paste a Google Cloud OAuth Client ID and secret.
5. In Google Cloud: create an OAuth client (Web application). Authorized JavaScript origin: `http://127.0.0.1:8000`. Authorized redirect URI: `https://YOUR-PROJECT.supabase.co/auth/v1/callback`.
6. In Supabase: **Authentication → URL configuration**. Add `http://127.0.0.1:8000` (and `http://127.0.0.1:8000/`) to redirect URLs.
7. Keep `.env` private. Never put the service role / secret key in JavaScript or Settings.
8. Restart `python server.py`. Open the app and choose **Continue with Google**.

The anon key is only used for Google sign-in. The Python server still uses the secret key for Twilio webhooks and storage.

Dialer Twilio credentials and session preferences are saved per Google account in `dialer_settings`. Each prospect keeps a timezone for display and filtering. Calls are not blocked by local time or a missing timezone.

## Upgrade

After pulling a new version, re-run [`schema.sql`](./schema.sql) in the Supabase SQL editor before restarting `server.py`. It is safe to run on an existing project. The dialer now records metrics through the `increment_metric` function defined there; until it exists, every metric update fails.

## Move existing local data

After running the SQL and configuring `.env`, you can run:

```powershell
python -m scripts.migrate_to_supabase --user-id YOUR-USER-UUID
```

`--user-id` is required. Sign in with Google once first, then copy your user id from **Authentication → Users** in Supabase. Every imported prospect, metric, and session row is attached to that account.
