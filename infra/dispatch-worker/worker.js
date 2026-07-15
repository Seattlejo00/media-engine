// Cloudflare Worker that triggers the Daily Episode workflow on time.
//
// GitHub's own cron scheduler is best-effort and has fired 1-6 hours late
// for this repo. Cloudflare cron triggers fire within seconds, so this
// Worker calls the workflow_dispatch API at the exact target time. The
// workflow's schedule trigger stays in place as a delayed backup — its
// "already published" guard makes the duplicate run a no-op.
//
// Setup: see README.md in this directory.

const WORKFLOW_DISPATCH_URL =
  "https://api.github.com/repos/Seattlejo00/media-engine/actions/workflows/daily-episode.yml/dispatches";

export default {
  async scheduled(event, env, ctx) {
    const resp = await fetch(WORKFLOW_DISPATCH_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_PAT}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        // GitHub's API rejects requests without a User-Agent
        "User-Agent": "context-window-dispatch-worker",
      },
      body: JSON.stringify({ ref: "main" }),
    });

    // Success is 204 No Content. Throw on anything else so the failure
    // shows up in the Worker's Cron Events log instead of passing silently.
    if (resp.status !== 204) {
      const body = await resp.text();
      throw new Error(`workflow_dispatch failed: HTTP ${resp.status} ${body}`);
    }
  },
};
