# Secrets setup — cloud pipeline

The pipeline now runs in GitHub Actions instead of a local PC, so every key
that used to live in `.env` becomes a **repository secret** on THIS repo
(`media-engine`): GitHub → media-engine → **Settings → Secrets and variables →
Actions → New repository secret**. Names must match exactly.

Work through Tier 1 first — that's enough for daily episodes with YouTube
uploads and website articles. Everything else can wait.

---

## Tier 1 — required (episodes won't run without these)

### 1. `OPENAI_API_KEY`
Used for: ChatGPT's dialogue lines, both TTS voices, YouTube title generation.

- Go to https://platform.openai.com → sign in → Settings → API keys → Create new secret key.
- Make sure the account has billing/credits (Settings → Billing).
- Copy the `sk-...` key into a secret named `OPENAI_API_KEY`.

### 2. `ANTHROPIC_API_KEY`
Used for: script structure + Claude's dialogue lines.

- https://console.anthropic.com → API Keys → Create Key.
- Needs billing configured on the account.
- Secret name: `ANTHROPIC_API_KEY`.
- (The same key also goes in the **ai-daily-site** repo's secrets under the
  same name, for the text-only fallback workflow there.)

### 3. `NEWS_API_KEY`
Used for: topic discovery (free tier, 100 requests/day is plenty).

- https://newsapi.org → Get API Key → register → key is shown on your account page.
- Secret name: `NEWS_API_KEY`.

### 4–6. YouTube OAuth: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
Used for: uploading episodes and Shorts to the channel.
This is the only multi-step one, and the refresh token **must be minted on
your own computer** because it needs a browser sign-in.

**a) Google Cloud project + OAuth client:**
1. https://console.cloud.google.com → create a project (e.g. "ai-daily").
2. APIs & Services → Library → search "YouTube Data API v3" → Enable.
3. APIs & Services → OAuth consent screen:
   - User type: External → fill in app name + your email → Save.
   - **Important:** under Audience / Publishing status, click **Publish app**
     (move out of "Testing"). Tokens minted while in Testing mode expire after
     7 days, which would silently kill uploads a week in.
4. APIs & Services → Credentials → Create Credentials → OAuth client ID →
   Application type: **Desktop app**.
5. Copy the Client ID → secret `YOUTUBE_CLIENT_ID`, and the Client secret →
   secret `YOUTUBE_CLIENT_SECRET`.

**b) Mint the refresh token (on your PC, one time):**
```
git clone https://github.com/Seattlejo00/media-engine.git
cd media-engine
pip install google-auth-oauthlib python-dotenv
```
Create a `.env` file containing just:
```
YOUTUBE_CLIENT_ID=<the client id>
YOUTUBE_CLIENT_SECRET=<the client secret>
```
Then run:
```
python get_youtube_token.py
```
A browser opens — **sign in with the Google account that owns the
@TheAIDaily26 channel** and approve. The script prints
`YOUTUBE_REFRESH_TOKEN=...` — copy the value into a secret named
`YOUTUBE_REFRESH_TOKEN`, then delete the local `.env`.

### 7. `SITE_PUSH_TOKEN`
Used for: letting the workflow push the article to the `ai-daily-site` repo.
(New requirement — on the old PC this was your regular git login.)

- GitHub → your avatar → Settings → Developer settings →
  Personal access tokens → **Fine-grained tokens** → Generate new token.
- Repository access: **Only select repositories → ai-daily-site**.
- Permissions: Repository permissions → **Contents → Read and write**. Nothing else.
- Expiration: 1 year (put a calendar reminder to rotate it).
- Secret name: `SITE_PUSH_TOKEN`.

---

## Tier 2 — optional (features are skipped automatically if unset)

| Secret | Feature | Where |
|---|---|---|
| `GOOGLE_AI_API_KEY` | Gemini as Friday guest host | https://aistudio.google.com → Get API key |
| `XAI_API_KEY` | Grok as Friday guest host | https://console.x.ai |
| `TWITTER_API_KEY` / `TWITTER_API_SECRET` / `TWITTER_ACCESS_TOKEN` / `TWITTER_ACCESS_SECRET` | Auto-tweet episodes + clips | https://developer.x.com (see SETUP_TODO.txt) |
| `TIKTOK_ACCESS_TOKEN` | Auto-post clips to TikTok | https://developers.tiktok.com (see SETUP_TODO.txt) |
| `R2_ENDPOINT_URL` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` / `R2_PUBLIC_URL` | Podcast audio hosting (Spotify/Apple) | https://cloudflare.com (see SETUP_TODO.txt) |

---

## After the secrets are in

1. Actions tab → **Daily Episode** → **Run workflow** to test end-to-end.
2. Watch the log; the run takes roughly 20–40 minutes (video render is the
   slow part). Logs, transcript, and the cost report are attached to the run
   as an artifact.
3. If it succeeds you'll have: a YouTube upload, Shorts, and a new article on
   the website — all from one run.

## Old keys

Everything that lived in `.env` on the retired PC should be treated as
compromised-by-abandonment: revoke old keys in each provider's console as you
create the new ones.
