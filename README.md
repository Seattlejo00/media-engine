# Distomos Media Engine

One repository for producing and publishing the AI-hosted daily show.

## Repository layout

- `main.py` — daily episode orchestrator
- `pipeline/` — research, scripts, TTS, audio, video, clips, and artwork
- `distribution/` — audio hosting, YouTube, TikTok, and social publishing
- `sites/ai-daily/` — generated publication, archive, and transcripts
- `sites/distomos/` — Distomos parent-brand website

## Run the media engine

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --dry-run
```

See `SETUP_SECRETS.md` and `SETUP_TODO.txt` for service configuration.

## Run Distomos locally

```bash
cd sites/distomos
npm install
npm run dev
```

## Rebuild AI Daily

```bash
python sites/ai-daily/scripts/build.py
```

The scheduled GitHub workflow runs the media engine, publishes the new episode
into `sites/ai-daily`, rebuilds the static publication, and commits the generated
episode files back to this repository.
