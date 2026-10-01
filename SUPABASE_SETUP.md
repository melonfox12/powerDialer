# Supabase storage setup

The app can store prospects, transcripts, statuses, and call metrics in Supabase. Supabase credentials are only read by the Python server; they are never sent to the browser. If neither Supabase setting is present, the app continues to use local `crm_data.json` and `metrics.json`. If only one setting is configured or the remote database is unavailable, startup fails rather than silently switching storage.

## Configure

1. Create a Supabase project.
2. In the SQL editor, run [`supabase_schema.sql`](./supabase_schema.sql). If you already installed an earlier version of this schema, run the updated script again to create the session history table.
3. Add the settings shown in [`.env.example`](./.env.example) to the private `.env` file, then set:
   - `SUPABASE_URL`: the project URL, such as `https://your-project.supabase.co`
   - `SUPABASE_SECRET_KEY`: a server-only Supabase secret key (`sb_secret_...`), or for legacy projects, `SUPABASE_SERVICE_ROLE_KEY`
4. Keep `.env` private. Never put the service role key in JavaScript, HTML, a committed file, or a public client setting.
5. Start the app. Startup performs read-only checks against the prospects and metrics tables. `/api/health` reports the selected storage backend and its current read availability.

Do not use a Supabase publishable/anon key for server storage. It is intended for clients and does not have the service privileges required by this app's row-level-security-protected tables. The app rejects publishable/anon keys during startup.

The schema enables row-level security and grants the app's service role access. Do not use an anon/public key as the server key.

## Move existing local data

After running the SQL and configuring `.env`, run:

```powershell
.\.venv\Scripts\python.exe .\migrate_to_supabase.py
```

The migration imports `crm_data.json` and `metrics.json`. It can safely resume a partial migration when the existing remote rows still match the local data; it stops if it finds differing or unrelated rows rather than overwriting them. The migration does not delete or modify the local files. Run it before switching the app to Supabase.

Once the app starts with both Supabase settings configured, Supabase is authoritative; the app does not mirror writes into the local JSON files. If the schema does not exist yet, startup reports the database error instead of falling back to local files.
