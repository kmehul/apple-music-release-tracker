# Apple Music new-release tracker

Get a **phone push + email** the moment one of your favourite artists drops a
single, EP, or album — instead of relying on Apple Music's flaky notifications.

It works by checking Apple's free [iTunes lookup API](https://performance-partners.apple.com/search-api)
for each artist on a schedule, remembering what it has already seen, and alerting
you on anything new (including pre-orders/upcoming releases). No Apple Developer
account, no paid services — it runs for free on GitHub Actions.

## How it works

```
artists.txt ──► resolve names to Apple IDs ──► look up each artist's releases
                                                        │
                     seen.json (already-announced) ◄────┤ new? 
                                                        ▼
                                         ntfy push  +  email
```

- **`artists.txt`** — your list, one artist name per line. This is the only file you edit.
- **`artist_ids.json`** — auto-generated cache of name → Apple ID.
- **`seen.json`** — auto-generated log of releases already announced (so nothing repeats).

The first run just records everything as a **baseline** (no notification flood).
Every run after that alerts you only on genuinely new drops.

## Maintaining your artist list

Open `artists.txt` and:
- **Add** an artist → add a line with their name.
- **Remove** an artist → delete their line.

Commit and push. That's it — IDs resolve automatically on the next run.

**Adding an artist won't spam you with their old music.** A newly-added artist
is baselined silently (their existing catalogue is recorded, not announced), and
you're only alerted to releases that appear *after* you add them — tracked in
`baselined.json`.

## One-time setup

### 1. Put this on GitHub
Create a new repository (private is fine) and push these files to it.

### 2. Set up push notifications (ntfy — free)
1. Install the **ntfy** app ([iOS](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
2. Tap **+** and subscribe to a topic. Pick something long and unguessable,
   e.g. `apple-releases-k7m2x9q` (anyone who knows the topic can send you pushes).
3. Remember that topic name for step 4.

### 3. Set up email (Gmail — free)
1. Enable 2-Step Verification on your Google account.
2. Create an **App Password**: Google Account → Security → App passwords.
3. Copy the 16-character password for step 4.

### 4. Add repository secrets
In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add these:

| Secret | Value |
| --- | --- |
| `NTFY_TOPIC` | the topic from step 2, e.g. `apple-releases-k7m2x9q` |
| `EMAIL_TO` | where alerts go, e.g. `you@gmail.com` |
| `EMAIL_FROM` | the Gmail you're sending from |
| `SMTP_USER` | the same Gmail address |
| `SMTP_PASS` | the 16-char app password from step 3 |

Optional — under the **Variables** tab, add `ITUNES_COUNTRY` (e.g. `IN`, `US`,
`GB`) to match your Apple Music storefront. Defaults to `IN`.

### 5. Kick it off
Go to the **Actions** tab → **Check for new releases** → **Run workflow**.
The first run sets the baseline. From then on it runs automatically every 6
hours and notifies you of anything new.

## Run it locally (optional, for testing)

No dependencies — just Python 3.9+.

```bash
export NTFY_TOPIC="apple-releases-k7m2x9q"
export EMAIL_TO="you@gmail.com"
export EMAIL_FROM="you@gmail.com"
export SMTP_USER="you@gmail.com"
export SMTP_PASS="your-16-char-app-password"
export ITUNES_COUNTRY="IN"
python3 track_releases.py
```

Delete `seen.json` to reset the baseline. Leave the notification env vars unset
to do a dry run (it just prints what it finds).

## Tuning

- **Check more/less often** — edit the `cron` line in `.github/workflows/check.yml`.
- **How far back counts as "new"** — set `RECENT_DAYS` (default 45). This guards
  against re-announcing old albums if `seen.json` is ever lost.

## Never pauses

GitHub auto-disables scheduled workflows after 60 days of no repo activity. To
prevent that during a long stretch with no new releases, each run updates a
`.heartbeat` file with the current month and commits it — keeping the repo
active well inside the 60-day window, so the schedule runs forever untouched.
