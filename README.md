# Distomos Media Engine

One repository for producing and publishing the AI-hosted daily show.

## Repository layout

- `main.py` — daily episode orchestrator
- `pipeline/` — research, scripts, TTS, audio, video, clips, and artwork
- `distribution/` — audio hosting, YouTube, TikTok, and social publishing
- `sites/ai-daily/` — generated Context Window publication, archive, and transcripts
- `sites/distomos/` — Distomos parent-brand website

## Run the media engine

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --dry-run
```

See `SETUP_SECRETS.md` and `SETUP_TODO.txt` for service configuration.

## Add a one-off on-air note

For a manual GitHub Actions run, put the announcement in the **special_note**
field. The hosts will work it naturally into that episode's intro. From the
command line, use `python main.py --special-note "Your announcement"`.

For a future scheduled episode, add a date and note to `episode_notes.json`.
Date-keyed notes apply only to that production date, so they expire without a
cleanup run. Changing a note automatically regenerates the script-dependent
checkpoints while preserving the upload ledger.

## Run Distomos locally

```bash
cd sites/distomos
npm install
npm run dev
```

## Rebuild Context Window

```bash
python sites/ai-daily/scripts/build.py
```

The scheduled GitHub workflow runs the media engine, publishes the new episode
into `sites/ai-daily`, rebuilds the static publication, and commits the generated
episode files back to this repository.
