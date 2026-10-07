/**
 * Cloudflare Worker for apple-music-release-tracker: starts the release check at
 * exact times.
 *
 * GitHub's own scheduled runs started 2-6 hours late on this repo, and sometimes
 * not at all, whereas workflow_dispatch runs start within seconds, so Cloudflare
 * triggers the dispatch instead. Needs a GH_TOKEN secret (fine-grained PAT, this
 * repo only, Actions: read & write). Setup: "Exact-time checks (Cloudflare)" in
 * README.md.
 *
 * Cloudflare's free plan allows 5 Cron Triggers per account and the job tracker
 * already uses 3, so the four check times share one trigger:
 *
 *     37,41,47,53 0,6,12,18 * * *
 *
 * It fires 16 times a day; RUN_AT picks the four that count. Matching on the
 * scheduled time rather than the trigger text means a trigger typed with
 * different spacing still behaves the same.
 */

const REPO = "kmehul/apple-music-release-tracker";
const WORKFLOW = "check.yml";

// UTC time of each check -> the same moment in IST.
const RUN_AT = {
  "18:47": "00:17 IST", // catches releases that went live at midnight IST
  "00:53": "06:23 IST",
  "06:41": "12:11 IST",
  "12:37": "18:07 IST",
};

export default {
  async scheduled(event, env, ctx) {
    const utc = new Date(event.scheduledTime).toISOString().slice(11, 16);
    const slot = RUN_AT[utc];
    if (!slot) return; // one of the shared trigger's other 12 firings

    ctx.waitUntil((async () => {
      if (!env.GH_TOKEN) {
        console.log("GH_TOKEN missing — cannot dispatch");
        return;
      }
      const res = await fetch(
        `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
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
      console.log(`${slot} dispatch -> ${res.status} `
        + `${res.status === 204 ? "ok" : await res.text()}`);
    })());
  },
};
