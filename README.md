# Apple Music new-release tracker

Get an **email** when one of your favourite artists drops a single, EP, or
album — instead of relying on Apple Music's flaky notifications. It checks four
times a day, at 00:17, 06:23, 12:11 and 18:07 IST, so a release that goes live at
midnight IST reaches your inbox within about 20 minutes.

It works by checking Apple's free [iTunes lookup API](https://performance-partners.apple.com/search-api)
for each artist on a schedule, remembering what it has already seen, and emailing
you once something is actually out (pre-orders/upcoming releases are skipped until
they go live). No Apple Developer account, no paid services — it
runs for free on GitHub Actions.

## How it works

```
artists.txt ──► resolve names to Apple IDs ──► look up each artist's releases
                                                        │
                     seen.json (already-announced) ◄────┤ new? 
                                                        ▼
                                                      email
```

- **`artists.txt`** — your list, one artist name per line. This is the only file you edit.
- **`artist_ids.json`** — auto-generated cache of name → Apple ID.
- **`seen.json`** — auto-generated log of releases already announced (so nothing repeats).
- **`caught.json`** — auto-generated list of every release that's been emailed, oldest first.
  The "releases caught" stat on [github.com/kmehul](https://github.com/kmehul) counts it.

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

**Name mix-ups are skipped.** Apple sometimes lists a different artist who shares
the name on your artist's page (a "feat. Meduza" rap single turned up on
MEDUZA's). A release is only emailed if it credits your artist as Apple spells
them; extra capitals are fine ("Hiroyuki SAWANO"), dropped ones aren't ("Meduza"
isn't MEDUZA). Skipped releases are listed in `skipped.json`. Everything else on
the page — singles, EPs, albums, remixes, DJ mixes, compilations — is emailed.

## One-time setup

### 1. Put this on GitHub
Create a new repository (private is fine) and push these files to it.

### 2. Set up email (Gmail — free)
1. Enable 2-Step Verification on your Google account.
2. Create an **App Password**: Google Account → Security → App passwords.
3. Copy the 16-character password for step 3.

### 3. Add repository secrets
In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add these:

| Secret | Value |
| --- | --- |
| `EMAIL_TO` | where alerts go, e.g. `you@gmail.com` |
| `EMAIL_FROM` | the Gmail you're sending from |
| `SMTP_USER` | the same Gmail address |
| `SMTP_PASS` | the 16-char app password from step 2 |

Optional — under the **Variables** tab, add `ITUNES_COUNTRY` (e.g. `IN`, `US`,
`GB`) to match your Apple Music storefront. Defaults to `IN`.

### 4. Kick it off
Go to the **Actions** tab → **Check for new releases** → **Run workflow**.
The first run sets the baseline. From then on it runs four times a day, started
by Cloudflare (see below), and emails you anything new.

## Exact-time checks (Cloudflare)

GitHub's own scheduled runs started 2-6 hours late here, and sometimes not at
all. Runs started on request (`workflow_dispatch`) begin within seconds, so a free
Cloudflare Worker ([`cloudflare-worker.js`](cloudflare-worker.js)) requests one at
**00:17, 06:23, 12:11 and 18:07 IST**. The 00:17 run catches releases that went
live at midnight IST. Six minutes after each check, the same Worker refreshes the
tracker card on [github.com/kmehul](https://github.com/kmehul), whose own hourly
GitHub schedule was running only every 4-6 hours.

1. **Create a GitHub token.** Avatar → *Settings* → *Developer settings* →
   *Personal access tokens* → **Fine-grained tokens** → *Generate new token*:
   - Name: `cloudflare-release-tracker-cron`
   - Expiration: **No expiration**, so it can't lapse silently on a forgotten date
   - Repository access: *Only select repositories* → `apple-music-release-tracker`
     **and** `kmehul` (the profile repo, for the card refresh)
   - Permissions → Repository permissions → **Actions: Read and write**
   - Generate, then copy the token.
2. **Create the Worker.** <https://dash.cloudflare.com> → *Workers & Pages* →
   *Create* → *Create Worker* → name it `release-tracker-cron` → *Deploy*. Then
   *Edit code*, replace everything with
   [`cloudflare-worker.js`](cloudflare-worker.js), and *Deploy*.
3. **Give it the token.** Worker → *Settings* → *Variables and Secrets* → *Add* →
   type **Secret**, name `GH_TOKEN`, paste the token → *Deploy*.
4. **Add the schedule.** Worker → *Settings* → *Trigger Events* → *Add* →
   *Cron Triggers*, and enter exactly:

   ```
   37,41,43,47,53,59 0,6,12,18 * * *
   ```

   This is one trigger for everything. Cloudflare's free plan allows 5 per
   account and the job tracker uses 3. Cron runs every listed minute in every
   listed hour, in UTC (IST = UTC + 5:30), so it fires 6 × 4 = 24 times a day.
   The Worker acts on 8 of those: the four checks and the four card refreshes.

Each dispatch is logged in the Worker's *Logs* tab ("00:17 IST release check ->
204 ok"), and the runs show up in the Actions tab as *workflow_dispatch*.

## Run it locally (optional, for testing)

No dependencies — just Python 3.9+.

```bash
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

- **Change the check times** — edit `RUN_AT` in `cloudflare-worker.js` (UTC times),
  make sure the Cloudflare cron trigger fires at those minutes and hours, and
  redeploy the Worker. Update the hour threshold in `watchdog.yml` if the longest
  gap between checks grows past 8 hours.
- **How far back counts as "new"** — set `RECENT_DAYS` (default 120). Any
  unseen release dated within this window is emailed; older ones are recorded
  silently, so a catalogue re-listing can't flood you with old albums.

## Never pauses

The release check has no GitHub schedule to disable: Cloudflare starts it. The
daily watchdog is scheduled, and GitHub auto-disables scheduled workflows after
60 days of no repo activity, so each release check updates a `.heartbeat` file
with the current month and commits it, keeping the repo active well inside that
window. If the checks themselves ever stop, the watchdog's failure email says so.
