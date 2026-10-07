/**
 * Cloudflare Worker for apple-music-release-tracker: starts the release check at
 * exact times, then refreshes the tracker card on github.com/kmehul.
 *
 * GitHub's own scheduled runs started 2-6 hours late on these repos, and sometimes
 * not at all, whereas workflow_dispatch runs start within seconds, so Cloudflare
 * triggers the dispatch instead. Needs a GH_TOKEN secret: a fine-grained PAT for
 * the two repos below, Actions: read & write. Setup: "Exact-time checks
 * (Cloudflare)" in README.md.
 *
 * Cloudflare's free plan allows 5 Cron Triggers per account and the job tracker
 * already uses 3, so everything shares one trigger:
 *
 *     37,41,43,47,53,59 0,6,12,18 * * *
 *
 * Cron runs every listed minute in every listed hour (UTC): 6 x 4 = 24 times a
 * day. RUN_AT picks the 8 that do something. Matching on the scheduled time
 * rather than the trigger text means a trigger typed with different spacing
 * still behaves the same.
 */

const TRACKER = "kmehul/apple-music-release-tracker";
const PROFILE = "kmehul/kmehul";

// UTC time -> [repo, workflow, what it is in IST]. The four release checks are
// the times on the profile card. Each is followed 6 minutes later by a refresh
// of the card's numbers, once the check (about 2 minutes) has saved caught.json.
const RUN_AT = {
  "18:47": [TRACKER, "check.yml", "00:17 IST release check"], // catches midnight IST releases
  "18:53": [PROFILE, "tracker-stats.yml", "00:23 IST card refresh"],
  "00:53": [TRACKER, "check.yml", "06:23 IST release check"],
  "00:59": [PROFILE, "tracker-stats.yml", "06:29 IST card refresh"],
  "06:41": [TRACKER, "check.yml", "12:11 IST release check"],
  "06:47": [PROFILE, "tracker-stats.yml", "12:17 IST card refresh"],
  "12:37": [TRACKER, "check.yml", "18:07 IST release check"],
  "12:43": [PROFILE, "tracker-stats.yml", "18:13 IST card refresh"],
};

export default {
  async scheduled(event, env, ctx) {
    const utc = new Date(event.scheduledTime).toISOString().slice(11, 16);
    const job = RUN_AT[utc];
    if (!job) return; // one of the shared trigger's other 16 firings
    const [repo, workflow, label] = job;

    ctx.waitUntil((async () => {
      if (!env.GH_TOKEN) {
        console.log("GH_TOKEN missing — cannot dispatch");
        return;
      }
      const res = await fetch(
        `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.GH_TOKEN}`,
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "apple-music-release-tracker-cron",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ ref: "main" }),
        },
      );
      // 204 = accepted. Anything else shows up in the Worker's logs.
      console.log(`${label} -> ${res.status} `
        + `${res.status === 204 ? "ok" : await res.text()}`);
    })());
  },
};
