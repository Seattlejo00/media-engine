# Daily Episode dispatch Worker

A Cloudflare Worker that kicks off the **Daily Episode** GitHub workflow at
the exact target time each morning.

## Why this exists

The workflow's own `schedule:` cron is queued best-effort by GitHub and has
fired **1–6 hours late** (Jul 12: 6h, Jul 13: 2.5h, Jul 15: 1.4h — even
after moving to an off-peak minute). Cloudflare cron triggers fire within
seconds. With the pipeline taking 6–9 minutes, a 9:45 UTC trigger has the
episode fully live by ~9:55 UTC (5:55 AM ET), ahead of the 6 AM ET target.

The workflow's GitHub cron (`52 9 * * *`) stays in place as a backup. When
it eventually fires, the "already published" guard sees today's episode and
skips — you'll see a short no-op run in the Actions tab each day, which is
expected.

## One-time setup (~15 minutes)

### 1. GitHub token (~3 min)

The Worker needs a fine-grained PAT that may trigger workflows on this repo.
Two options:

- **Reuse:** edit the existing `GH_SECRETS_PAT` token (GitHub → Settings →
  Developer settings → Fine-grained tokens) and add **Actions: Read and
  write** to its repository permissions. No new token to manage.
- **Or create fresh:** same place → *Generate new token* → Repository
  access: only `media-engine` → Permissions → **Actions: Read and write**.

Either way, copy the `github_pat_...` value for step 2. Note the token's
expiry date — when it lapses, the Worker stops silently and the show falls
back to GitHub's (late) cron. Put the renewal date in your calendar.

### 2. Cloudflare Worker (~10 min, dashboard path)

1. [dash.cloudflare.com](https://dash.cloudflare.com) → **Workers & Pages**
   → **Create** → **Create Worker**. Name it `daily-episode-dispatch`,
   deploy the hello-world it scaffolds.
2. **Edit code** → replace the contents with [`worker.js`](./worker.js)
   from this directory → **Deploy**.
3. Worker → **Settings** → **Variables and Secrets** → **Add** → type
   *Secret*, name `GITHUB_PAT`, value = the token from step 1.
4. Worker → **Settings** → **Triggers** → **Cron Triggers** → **Add** →
   `45 9 * * *` (UTC).

CLI alternative: `npx wrangler deploy` from this directory (uses
`wrangler.toml`), then `npx wrangler secret put GITHUB_PAT`.

### 3. Verify

Temporarily set the cron trigger to a couple of minutes from now, wait for
it to fire, and confirm a `workflow_dispatch` run appears in the repo's
Actions tab (it will publish or no-op depending on whether today's episode
already exists). Then set the cron back to `45 9 * * *`. Failures show up
under the Worker's **Cron Events** log.

## Notes

- The only credential involved is the GitHub PAT, stored as a Worker
  secret. Cloudflare-side no API key is needed.
- Free plan is fine: one request per day.
- To change the show's publish time, update the cron here (this is now the
  real schedule) — the GitHub workflow cron only needs to move if you want
  the backup window to follow.
