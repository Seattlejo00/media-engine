#!/usr/bin/env python3
"""
Static site generator for The AI Daily.

Reads static/articles.json + static/articles/<date>.html fragments
(published by media-engine's publish_site.py, which also invokes this
script after every episode) and writes:

    index.html                 homepage
    episodes/index.html        archive
    episodes/<date>.html       transcript pages
    about.html                 about the show
    tiktok-callback.html       OAuth redirect landing page

Design: editorial layout in the show's palette (indigo ink, cream
paper, Claude orange + ChatGPT green). No dependencies — stdlib only.
"""

import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://theaidaily.distomostech.com"
YT_CHANNEL = "https://www.youtube.com/@TheAIDaily26"

SPEAKER_COLORS = {"Claude": "#cc7832", "ChatGPT": "#10a37f",
                  "Gemini": "#4285f4", "Grok": "#ef4444"}

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def fmt_date(date_str: str) -> tuple[str, str, str]:
    """'2026-07-11' -> ('JUL 11', '2026', 'Friday, July 11')"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (f"{MONTHS[d.month - 1]} {d.day:02d}", str(d.year),
            d.strftime("%A, %B %d").replace(" 0", " "))


def fmt_duration(seconds) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def esc(s) -> str:
    return html.escape(str(s or ""))


def page(title: str, desc: str, path: str, body: str, active: str = "") -> str:
    def nav(href: str, label: str, key: str) -> str:
        return f'<a href="{href}"{" style=\"color:var(--gpt)\"" if active == key else ""}>{label}</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE_URL}{path}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:image" content="{SITE_URL}/podcast-cover.png">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/rss+xml" title="The AI Daily" href="{SITE_URL}/feed.xml">
<link rel="icon" href="/podcast-cover.png">
<link rel="stylesheet" href="/static/site.css">
</head>
<body>
<header class="site-header wrap">
  <a class="logo" href="/"><i></i>THE AI DAILY<small>BY DISTOMOS</small></a>
  <nav>{nav("/episodes/", "Episodes", "episodes")}{nav("/about.html", "About", "about")}<a href="/feed.xml">RSS</a></nav>
  <a class="watch" href="{YT_CHANNEL}" target="_blank" rel="noopener">Watch on YouTube <span>&#8599;</span></a>
</header>
<main>
{body}
</main>
<footer><div class="wrap footer-inner">
  <a class="logo" href="/"><i></i>THE AI DAILY</a>
  <p>AI news, hosted by AIs.<br>A Distomos publication.</p>
  <div><a href="/episodes/">Episodes</a><a href="/about.html">About</a><a href="/feed.xml">RSS</a><a href="/privacy.html">Privacy</a><a href="/terms.html">Terms</a><a href="{YT_CHANNEL}" target="_blank" rel="noopener">YouTube</a></div>
  <small>&copy; {datetime.now().year} DISTOMOS</small>
</div></footer>
</body>
</html>
"""


def audio_block(ep: dict) -> str:
    """Audio player when we have a podcast MP3, YouTube button otherwise."""
    dur = fmt_duration(ep.get("duration_seconds"))
    if ep.get("podcast_url"):
        return f"""<div class="audio-player" data-src="{esc(ep["podcast_url"])}">
  <button class="play" aria-label="Play episode">&#9654;</button>
  <div class="audio-track"><div class="time"><span class="state">LISTEN NOW</span><span>{dur or "&nbsp;"}</span></div><div class="track"><i></i></div></div>
</div>
<script>
(function(){{var w=document.currentScript.previousElementSibling,b=w.querySelector('.play'),
s=w.querySelector('.state'),bar=w.querySelector('.track i'),t=w.querySelector('.track'),
a=new Audio(w.dataset.src);b.onclick=function(){{if(a.paused){{a.play();b.innerHTML='&#10074;&#10074;';s.textContent='PLAYING';}}else{{a.pause();b.innerHTML='&#9654;';s.textContent='PAUSED';}}}};
a.ontimeupdate=function(){{bar.style.width=(a.currentTime/(a.duration||1))*100+'%';}};
a.onended=function(){{b.innerHTML='&#9654;';s.textContent='LISTEN AGAIN';}};
t.onclick=function(e){{var r=t.getBoundingClientRect();a.currentTime=((e.clientX-r.left)/r.width)*(a.duration||0);}};}})();
</script>"""
    if ep.get("youtube_url"):
        return f'<a class="yt-button" href="{esc(ep["youtube_url"])}" target="_blank" rel="noopener">&#9654;&nbsp;&nbsp;Watch today\'s episode</a>'
    return ""


def platforms_row(ep: dict) -> str:
    links = ['<span>LISTEN ON</span>']
    if ep.get("youtube_url"):
        links.append(f'<a href="{esc(ep["youtube_url"])}" target="_blank" rel="noopener">YouTube &#8599;</a>')
    links.append('<a href="/feed.xml">RSS &#8599;</a>')
    return f'<div class="platforms">{"".join(links)}</div>'


def score_card(ep: dict) -> str:
    scores = ep.get("scores")
    if not scores or not scores.get("overall"):
        return ""
    date_label, _, _ = fmt_date(ep["date"])
    rows = ""
    for label, value in (scores.get("categories") or {}).items():
        try:
            pct = max(0, min(100, float(value) * 10))
        except (TypeError, ValueError):
            continue
        rows += (f'<div class="score-row"><span>{esc(label)}</span>'
                 f'<i><b style="width:{pct:.0f}%"></b></i><strong>{esc(value)}</strong></div>')
    return f"""<aside class="score-card">
  <div class="section-kicker">TODAY'S AI SCORE <span>{date_label}</span></div>
  <div class="score-total"><strong>{esc(scores["overall"])}</strong><small>/ 10</small></div>
  <p>{esc(scores.get("label", ""))}</p>
  <div class="scores">{rows}</div>
  <small class="method">Scored daily by impact, novelty &amp; reach</small>
</aside>"""


def story_grid(ep: dict) -> str:
    topics = (ep.get("topics") or [])[:4]
    if not topics:
        return ""
    cards = ""
    for i, t in enumerate(topics, 1):
        src = ""
        if t.get("url"):
            src = f'<a class="src" href="{esc(t["url"])}" target="_blank" rel="noopener">{esc(t.get("source") or "Source")} &#8599;</a>'
        cards += f"""<article>
  <div class="story-meta"><span>{i:02d}</span><b>{esc(t.get("category", "news"))}</b></div>
  <h3>{esc(t.get("title"))}</h3>
  <p>{src}</p>
</article>"""
    return f"""<section class="stories wrap">
  <div class="section-heading"><div><span>01</span><h2>Today's stories</h2></div>
  <a href="/episodes/{ep["date"]}.html">Read the transcript <b>&#8599;</b></a></div>
  <div class="story-grid">{cards}</div>
</section>"""


def episode_rows(episodes: list[dict], limit: int | None = None) -> str:
    rows = ""
    for ep in episodes[:limit] if limit else episodes:
        date_label, year, _ = fmt_date(ep["date"])
        dur = fmt_duration(ep.get("duration_seconds"))
        rows += f"""<a class="episode-row" href="/episodes/{ep["date"]}.html">
  <time>{date_label}<small>{year}</small></time>
  <h3>{esc(ep["title"])}</h3>
  <span class="listen-icon">&#9654;</span><b>{dur}</b>
</a>"""
    return rows


def build_index(episodes: list[dict]) -> str:
    latest = episodes[0]
    _, _, long_date = fmt_date(latest["date"])
    date_label, _, _ = fmt_date(latest["date"])
    ep_num = len(episodes)
    scorecard = score_card(latest)
    feature_cols = "" if scorecard else ' style="grid-template-columns:1fr"'

    body = f"""<section class="hero wrap">
  <div class="eyebrow"><span class="live-dot"></span>{long_date.upper()} &middot; EPISODE {ep_num}</div>
  <h1>The most important<br>AI news. <em>Hosted by AIs.</em></h1>
  <div class="hero-bottom">
    <p class="dek">Claude and ChatGPT break down what changed in AI today, why it matters, and what comes next — every morning.</p>
    <div class="hosts"><span class="h-claude"><b></b>Claude &middot; Anthropic</span><span class="h-gpt"><b></b>ChatGPT &middot; OpenAI</span></div>
  </div>
</section>

<section class="feature wrap"{feature_cols}>
  <div class="feature-main">
    <div class="section-kicker">TODAY'S EPISODE <span>{date_label}</span></div>
    <h2>{esc(latest["title"])}</h2>
    {audio_block(latest)}
    {platforms_row(latest)}
  </div>
  {scorecard}
</section>

{story_grid(latest)}

<section class="archive wrap">
  <div class="section-heading"><div><span>02</span><h2>Previous episodes</h2></div>
  <a href="/episodes/">View the archive <b>&#8599;</b></a></div>
  <div class="episode-list">{episode_rows(episodes, limit=6)}</div>
</section>"""
    return page("The AI Daily — AI news, hosted by AIs",
                "Claude and ChatGPT break down the day's most important AI news. "
                "A daily podcast on YouTube, Spotify, and Apple Podcasts.",
                "/", body)


def build_archive(episodes: list[dict]) -> str:
    body = f"""<div class="inner wrap">
  <div class="page-intro">
    <p>THE ARCHIVE</p>
    <h1>Every signal.<br><em>None of the noise.</em></h1>
    <span>{len(episodes)} episode{"s" if len(episodes) != 1 else ""} &middot; Updated every day</span>
  </div>
  <div class="episode-list" style="margin-top:70px">{episode_rows(episodes)}</div>
</div>"""
    return page("Episodes — The AI Daily", "Every episode of The AI Daily.",
                "/episodes/", body, active="episodes")


def build_episode(ep: dict, ep_num: int) -> str | None:
    fragment_path = ROOT / "static" / "articles" / ep["article_file"]
    if not fragment_path.exists():
        return None
    fragment = fragment_path.read_text(encoding="utf-8")
    date_label, year, long_date = fmt_date(ep["date"])

    body = f"""<div class="inner wrap">
  <div class="episode-head">
    <p>EPISODE {ep_num} &middot; {long_date.upper()}, {year}</p>
    <h1>{esc(ep["title"])}</h1>
    <p class="standfirst">{esc(ep.get("description"))}</p>
    {audio_block(ep)}
    {platforms_row(ep)}
  </div>
  <article class="transcript">
{fragment}
  </article>
</div>"""
    return page(f'{ep["title"]} — The AI Daily', ep.get("description", ""),
                f'/episodes/{ep["date"]}.html', body, active="episodes")


def build_about(episodes: list[dict]) -> str:
    body = f"""<div class="inner wrap">
  <div class="page-intro">
    <p>ABOUT THE SHOW</p>
    <h1>AI news,<br><em>hosted by AIs.</em></h1>
  </div>
  <div class="about-grid">
    <h2>The first daily news show produced and hosted entirely by AI.</h2>
    <div>
      <p>Every morning, an automated pipeline reads the day's AI news, picks the
      stories that matter, and hands them to two hosts — Claude and ChatGPT —
      who discuss them as themselves. The episode is produced, scored,
      published and distributed with no human in the loop.</p>
      <p>New episodes daily on YouTube, with full transcripts here.</p>
      <div class="rss-box"><code>{SITE_URL}/feed.xml</code></div>
    </div>
  </div>
  <div class="host-cards">
    <div class="host-card"><b style="background:#cc7832">C</b><h3>Claude</h3><small>Anthropic &middot; Host</small></div>
    <div class="host-card"><b style="background:#10a37f">C</b><h3>ChatGPT</h3><small>OpenAI &middot; Host</small></div>
    <div class="host-card"><b style="background:#4285f4">G</b><h3>Gemini</h3><small>Google &middot; Friday guest</small></div>
    <div class="host-card"><b style="background:#ef4444">G</b><h3>Grok</h3><small>xAI &middot; Friday guest</small></div>
  </div>
</div>"""
    return page("About — The AI Daily",
                "The first daily news show produced and hosted entirely by AI.",
                "/about.html", body, active="about")


def build_callback() -> str:
    body = """<div class="inner wrap"><div class="page-intro">
  <p>AUTHORIZATION COMPLETE</p>
  <h1>You can close<br><em>this tab.</em></h1>
  <span>Copy the full URL from the address bar back into the token script.</span>
</div></div>"""
    return page("TikTok authorization — The AI Daily", "OAuth redirect landing page.",
                "/tiktok-callback", body)


def main() -> None:
    articles_path = ROOT / "static" / "articles.json"
    episodes = json.loads(articles_path.read_text(encoding="utf-8"))
    episodes.sort(key=lambda e: e["date"], reverse=True)
    if not episodes:
        raise SystemExit("articles.json is empty — nothing to build")

    (ROOT / "episodes").mkdir(exist_ok=True)

    (ROOT / "index.html").write_text(build_index(episodes), encoding="utf-8")
    (ROOT / "episodes" / "index.html").write_text(build_archive(episodes), encoding="utf-8")
    (ROOT / "about.html").write_text(build_about(episodes), encoding="utf-8")
    (ROOT / "tiktok-callback.html").write_text(build_callback(), encoding="utf-8")

    built = 0
    total = len(episodes)
    for i, ep in enumerate(episodes):
        ep_num = total - i
        html_page = build_episode(ep, ep_num)
        if html_page:
            (ROOT / "episodes" / f'{ep["date"]}.html').write_text(html_page, encoding="utf-8")
            built += 1

    print(f"Built homepage, archive, about + {built}/{total} episode pages")


if __name__ == "__main__":
    main()
