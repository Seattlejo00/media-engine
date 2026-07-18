# Colorado Tech Signal concept

Private, unofficial sales concept produced by Distomos for the Colorado
Technology Association. It is not produced by or endorsed by CTA.

The builder intentionally uses a single anchor and a local macOS placeholder
voice so it can render without provider credentials and without implying that
Claude or ChatGPT authored the one-off sales script. The script and timing are
designed to be locked before a separate premium-TTS voice audition.

From the repository root:

```bash
.venv/bin/python sales_demos/cta/build.py
```

Generated files are written under `output/cta-concept/<date>/single-anchor/`,
which is covered by the repository's existing `output/` ignore rule. Nothing is
uploaded.

## Premium voice audition

`build_voice_audition.py` loudness-matches three premium neural-TTS samples and
packages them as blinded Candidates A–C on a customer listening page. The
customer pack includes an explicit AI-generated-voice disclosure. The internal
provider-to-candidate mapping stays in `voice_audition_internal.json`.

```bash
.venv/bin/python sales_demos/cta/build_voice_audition.py \
  --marin /path/to/marin.mp3 \
  --coral /path/to/coral.mp3 \
  --nova /path/to/nova.mp3
```

## Selected premium episode voice

Candidate A (`marin`) is the selected customer voice. Generate any missing
numbered narration turns with the official OpenAI TTS API; existing turns are
preserved unless `--force` is supplied. Configure `OPENAI_API_KEY` locally in
the environment or `.env`—never paste it into chat.

```bash
.venv/bin/python sales_demos/cta/generate_premium_turns.py
```

After all 13 turns exist, render the customer-ready premium variant without
publishing:

```bash
.venv/bin/python sales_demos/cta/build.py \
  --premium-segments-dir output/cta-concept/<date>/premium-marin/raw_segments \
  --output-variant premium-marin
```
