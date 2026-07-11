#!/usr/bin/env python3
"""
Apple Music new-release tracker.

Reads a list of artist names from artists.txt, resolves each to an Apple
(iTunes) artist ID, checks for releases via the free iTunes lookup API, and
notifies you (phone push via ntfy + email) about anything new.

State lives in two JSON files so nothing gets re-announced:
  - artist_ids.json : cache of name -> Apple artist id (so we don't re-resolve)
  - seen.json       : every release id we've already recorded

Zero third-party dependencies: pure Python standard library.

Only actually-released items are announced — pre-orders/upcoming releases are
skipped until the day they go live. Config is read from environment variables
(see README.md):
  NTFY_TOPIC, NTFY_SERVER
  EMAIL_TO, EMAIL_FROM, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
  ITUNES_COUNTRY (default "US"), RECENT_DAYS (default 45)
"""

import json
import os
import smtplib
import ssl
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
ARTISTS_FILE = ROOT / "artists.txt"
IDS_FILE = ROOT / "artist_ids.json"
SEEN_FILE = ROOT / "seen.json"
BASELINED_FILE = ROOT / "baselined.json"

COUNTRY = os.environ.get("ITUNES_COUNTRY", "IN")
RECENT_DAYS = int(os.environ.get("RECENT_DAYS", "45"))

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", EMAIL_FROM)
SMTP_PASS = os.environ.get("SMTP_PASS", "")

USER_AGENT = "apple-music-release-tracker/1.0 (+https://github.com)"


# ---------------------------------------------------------------- helpers ----
def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_artists():
    if not ARTISTS_FILE.exists():
        return []
    names = []
    for line in ARTISTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


# ----------------------------------------------------------- itunes calls ----
def resolve_artist(name, cache):
    """Return {'artistId', 'artistName'} for a name, using/filling the cache."""
    if name in cache:
        return cache[name]
    url = (
        "https://itunes.apple.com/search"
        f"?term={quote(name)}&entity=musicArtist&limit=1&country={COUNTRY}"
    )
    try:
        results = http_get_json(url).get("results", [])
    except Exception as exc:
        print(f"  ! search failed for {name!r}: {exc}")
        return None
    if not results:
        print(f"  ! could not resolve artist: {name!r}")
        cache[name] = None
        return None
    r = results[0]
    info = {"artistId": r["artistId"], "artistName": r.get("artistName", name)}
    cache[name] = info
    print(f"  resolved {name!r} -> {info['artistName']} ({info['artistId']})")
    time.sleep(1)  # be gentle with the API
    return info


def get_releases(artist_id):
    url = (
        "https://itunes.apple.com/lookup"
        f"?id={artist_id}&entity=album&limit=200&country={COUNTRY}"
    )
    results = http_get_json(url).get("results", [])
    return [item for item in results if item.get("wrapperType") == "collection"]


# ---------------------------------------------------------- notifications ----
def notify_ntfy(title, message, url):
    if not NTFY_TOPIC:
        return
    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "tags": ["musical_note"],
    }
    if url:
        payload["click"] = url
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        NTFY_SERVER,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as exc:
        print(f"  ! ntfy push failed: {exc}")


def notify_email(subject, body):
    if not (EMAIL_TO and EMAIL_FROM and SMTP_PASS):
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
    except Exception as exc:
        print(f"  ! email failed: {exc}")


# ------------------------------------------------------------------- main ----
def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    artists = read_artists()
    if not artists:
        print("No artists listed in artists.txt — nothing to do.")
        return

    ids_cache = load_json(IDS_FILE, {})
    seen = load_json(SEEN_FILE, None)
    baselined = load_json(BASELINED_FILE, None)
    first_run = seen is None
    if first_run:
        print("First run: establishing a baseline (no notifications this time).")
        seen = {}

    # Which artists have already been baselined. A newly-added artist gets its
    # existing catalogue recorded silently (like the initial run), so you're only
    # alerted to releases that appear AFTER you add them. On the first run under
    # this logic, treat every already-resolved artist as baselined.
    if baselined is None:
        baselined = [] if first_run else [str(v["artistId"]) for v in ids_cache.values() if v]
    baselined = set(str(x) for x in baselined)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)
    new_items = []

    for name in artists:
        info = resolve_artist(name, ids_cache)
        if not info:
            continue
        aid = str(info["artistId"])
        artist_is_new = aid not in baselined  # freshly added to artists.txt
        try:
            releases = get_releases(info["artistId"])
        except Exception as exc:
            print(f"  ! lookup failed for {name!r}: {exc}")
            continue

        for rel in releases:
            cid = rel.get("collectionId")
            if cid is None:
                continue
            cid = str(cid)
            if cid in seen:
                continue

            reldate = parse_date(rel.get("releaseDate"))
            # Skip pre-orders / not-yet-released items: don't record or notify
            # them, so they're caught the day they actually go live on Apple Music.
            if reldate is not None and reldate > now:
                continue

            record = {
                "name": rel.get("collectionName"),
                "artist": info["artistName"],
                "date": rel.get("releaseDate"),
                "url": rel.get("collectionViewUrl"),
            }
            seen[cid] = record  # record it so we never re-announce

            if first_run or artist_is_new:
                continue  # baseline silently (initial run, or a newly added artist)
            # Only notify for releases that are actually out and reasonably recent,
            # so a lost seen.json can't flood you with old back-catalogue.
            if reldate is not None and reldate >= cutoff:
                new_items.append(record)

        baselined.add(aid)
        time.sleep(1)

    save_json(IDS_FILE, ids_cache)
    save_json(SEEN_FILE, seen)
    save_json(BASELINED_FILE, sorted(baselined))

    if first_run:
        print(f"Baseline set with {len(seen)} known releases. Future runs notify on new ones.")
        return

    # Collapse duplicate editions of the same release — Apple often lists one
    # single under several collection IDs, so dedupe by artist + title.
    deduped, titles = [], set()
    for it in new_items:
        key = (it["artist"], it["name"])
        if key in titles:
            continue
        titles.add(key)
        deduped.append(it)
    new_items = deduped

    if not new_items:
        print("No new releases.")
        return

    # One push per release (so each buzzes your phone)...
    for it in new_items:
        day = (it["date"] or "?")[:10]
        title = f"{it['artist']} – {it['name']}"
        body = f"Out now ({day})\n{it['url'] or ''}".strip()
        notify_ntfy(title, body, it["url"])

    # ...and one combined email (so your inbox stays tidy).
    lines = []
    for it in new_items:
        day = (it["date"] or "?")[:10]
        lines.append(f"- {it['artist']} — {it['name']} (out now, {day})\n  {it['url'] or ''}")
    subject = f"🎵 {len(new_items)} new release(s) from your artists"
    notify_email(subject, "New releases from your tracked artists:\n\n" + "\n\n".join(lines))

    print(f"Notified about {len(new_items)} new release(s).")


if __name__ == "__main__":
    main()
