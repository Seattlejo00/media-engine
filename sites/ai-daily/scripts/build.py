#!/usr/bin/env python3
"""
Static site generator for The Context Window.

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
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://contextwindow.distomostech.com"
YT_CHANNEL = "https://www.youtube.com/@TheContextWindow-q1z"
SPOTIFY_SHOW = "https://open.spotify.com/show/033OoZlyZBlEwCd6kmNdpT"

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


def youtube_image(ep: dict) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]+)", ep.get("youtube_url") or "")
    return f"https://i.ytimg.com/vi/{match.group(1)}/maxresdefault.jpg" if match else f"{SITE_URL}/podcast-cover.png"


def page(title: str, desc: str, path: str, body: str, active: str = "",
         og_image: str | None = None, og_type: str = "website",
         extra_head: str = "") -> str:
    def nav(href: str, label: str, key: str) -> str:
        style = ' style="color:var(--gpt)"' if active == key else ''
        return f'<a href="{href}"{style}>{label}</a>'

    image = og_image or f"{SITE_URL}/podcast-cover.png"
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
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{SITE_URL}{path}">
<meta property="og:image" content="{esc(image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(image)}">
<link rel="icon" href="/podcast-cover.png">
<link rel="stylesheet" href="/static/site.css?v=2">
{extra_head}
<script>
  window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};
</script>
<script defer src="/_vercel/insights/script.js"></script>
<script>
  window.si = window.si || function () {{ (window.siq = window.siq || []).push(arguments); }};
</script>
<script defer src="/_vercel/speed-insights/script.js"></script>
</head>
<body>
<header class="site-header wrap">
  <a class="logo" href="/"><i></i>THE CONTEXT WINDOW<small>BY DISTOMOS</small></a>
  <nav>{nav("/episodes/", "Episodes", "episodes")}{nav("/scores/", "Scores", "scores")}{nav("/about.html", "About", "about")}</nav>
  <div class="header-platforms">
    <a class="platform-button spotify" href="{SPOTIFY_SHOW}" target="_blank" rel="noopener"><i></i>Spotify <b>&#8599;</b></a>
    <a class="platform-button youtube" href="{YT_CHANNEL}" target="_blank" rel="noopener"><i></i>YouTube <b>&#8599;</b></a>
  </div>
</header>
<main>
{body}
</main>
<footer><div class="wrap footer-inner">
  <a class="logo" href="/"><i></i>THE CONTEXT WINDOW</a>
  <p>AI news, hosted by AIs.<br>A Distomos publication.</p>
  <div><a href="/episodes/">Episodes</a><a href="/scores/">Score history</a><a href="/about.html">About</a><a href="/privacy.html">Privacy</a><a href="{SPOTIFY_SHOW}" target="_blank" rel="noopener">Spotify</a><a href="{YT_CHANNEL}" target="_blank" rel="noopener">YouTube</a></div>
  <small>&copy; {datetime.now().year} DISTOMOS</small>
</div></footer>
<script>
document.addEventListener('click',function(e){{var t=e.target.closest('[data-event]');if(t)window.va('event',{{name:t.dataset.event,data:{{href:t.getAttribute('href')||'',episode:t.dataset.episode||''}}}});}});
</script>
</body>
</html>
"""


def audio_block(ep: dict) -> str:
    """Audio player when we have a podcast MP3, YouTube button otherwise."""
    dur = fmt_duration(ep.get("duration_seconds"))
    if ep.get("podcast_url"):
        return f"""<div class="audio-player" data-src="{esc(ep["podcast_url"])}" data-episode="{esc(ep.get("date"))}">
  <button class="play" aria-label="Play episode">&#9654;</button>
  <div class="audio-track"><div class="time"><span class="state">LISTEN NOW</span><span><b class="elapsed">00:00</b> / <b class="duration">{dur or "00:00"}</b></span></div><input class="track" aria-label="Episode progress" type="range" min="0" max="1" step="1" value="0"></div>
  <button class="speed" aria-label="Playback speed">1×</button>
</div>
<script>
(function(){{var w=document.currentScript.previousElementSibling,b=w.querySelector('.play'),s=w.querySelector('.state'),
t=w.querySelector('.track'),el=w.querySelector('.elapsed'),du=w.querySelector('.duration'),sp=w.querySelector('.speed'),
a=new Audio(w.dataset.src),speeds=[1,1.25,1.5,2],si=0,ph=document.createElement('div'),visible=true;
ph.className='audio-placeholder';ph.style.height='1px';w.before(ph);function fmt(v){{v=Math.max(0,Math.floor(v||0));return String(Math.floor(v/60)).padStart(2,'0')+':'+String(v%60).padStart(2,'0')}}
function float(){{w.classList.toggle('is-floating',!a.paused&&!visible)}}
new IntersectionObserver(function(e){{visible=e[0].isIntersecting;float()}},{{threshold:.2}}).observe(ph);
b.onclick=function(){{if(a.paused){{a.play();window.va('event',{{name:'Episode play',data:{{episode:w.dataset.episode,surface:'website'}}}});}}else a.pause()}};
a.onplay=function(){{b.innerHTML='&#10074;&#10074;';s.textContent='PLAYING';float()}};
a.onpause=function(){{b.innerHTML='&#9654;';s.textContent='PAUSED';float()}};
a.onloadedmetadata=function(){{t.max=Math.floor(a.duration);du.textContent=fmt(a.duration)}};
a.ontimeupdate=function(){{t.value=Math.floor(a.currentTime);el.textContent=fmt(a.currentTime)}};
a.onended=function(){{s.textContent='LISTEN AGAIN';w.classList.remove('is-floating')}};
t.oninput=function(){{a.currentTime=Number(t.value)}};
sp.onclick=function(){{si=(si+1)%speeds.length;a.playbackRate=speeds[si];sp.textContent=speeds[si]+'×';window.va('event',{{name:'Playback speed',data:{{speed:speeds[si]}}}})}};}})();
</script>"""
    if ep.get("youtube_url"):
        return f'<a class="yt-button" data-event="YouTube episode click" data-episode="{esc(ep.get("date"))}" href="{esc(ep["youtube_url"])}" target="_blank" rel="noopener">&#9654;&nbsp;&nbsp;Watch today\'s episode</a>'
    return ""


def platforms_row(ep: dict) -> str:
    links = ['<span>LISTEN ON</span>']
    links.append(f'<a data-event="Spotify click" data-episode="{esc(ep.get("date"))}" href="{SPOTIFY_SHOW}" target="_blank" rel="noopener">Spotify &#8599;</a>')
    if ep.get("youtube_url"):
        links.append(f'<a data-event="YouTube click" data-episode="{esc(ep.get("date"))}" href="{esc(ep["youtube_url"])}" target="_blank" rel="noopener">YouTube &#8599;</a>')
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
  <div class="score-links"><a class="method" href="/scores/">View score history &#8599;</a><a class="method" href="/about.html#methodology">Methodology &#8599;</a></div>
</aside>"""


def briefing_snapshot(ep: dict) -> str:
    topics = [topic for topic in (ep.get("topics") or []) if topic.get("title")][:3]
    if not topics:
        return ""
    items = "".join(
        f'<li><b>{i:02d}</b><span>{esc(topic["title"])}</span></li>'
        for i, topic in enumerate(topics, 1)
    )
    why = esc(ep.get("description"))
    return f"""<section class="snapshot wrap">
  <div class="snapshot-title"><span>THE THREE THINGS TO KNOW</span><small>BEFORE YOU PRESS PLAY</small></div>
  <ol>{items}</ol>
  {f'<p><b>WHY IT MATTERS</b>{why}</p>' if why else ''}
</section>"""


def scored_episodes(episodes: list[dict]) -> list[dict]:
    """Return every episode carrying a valid overall score, oldest first."""
    return [
        ep for ep in reversed(episodes)
        if isinstance((ep.get("scores") or {}).get("overall"), (int, float))
    ]


def score_history_preview(episodes: list[dict]) -> str:
    history = scored_episodes(episodes)[-7:]
    if not history:
        return ""
    bars = "".join(
        f'''<a class="trend-day" href="/episodes/{ep["date"]}.html" aria-label="{esc(ep["date"])} score {esc(ep["scores"]["overall"])} out of 10">
  <strong>{esc(ep["scores"]["overall"])}</strong><i><b style="height:{float(ep["scores"]["overall"]) * 10:.0f}%"></b></i><span>{fmt_date(ep["date"])[0]}</span>
</a>'''
        for ep in history
    )
    return f"""<section class="score-trend wrap">
  <div><span class="section-number">SCORE LOG</span><h2>The signal over time.</h2><p>Every daily score is preserved with its category breakdown and episode record.</p><a href="/scores/">View the complete history &#8599;</a></div>
  <div class="trend-chart">{bars}</div>
</section>"""


def build_scores(episodes: list[dict]) -> str:
    history = scored_episodes(episodes)
    if not history:
        return page("AI Score History — The Context Window", "The complete Context Window AI Score history.", "/scores/", '<div class="inner wrap"><p>No scores published yet.</p></div>', active="scores")
    values = [float(ep["scores"]["overall"]) for ep in history]
    average = sum(values) / len(values)
    peak = max(history, key=lambda ep: float(ep["scores"]["overall"]))
    rows = ""
    for ep in reversed(history):
        scores = ep["scores"]
        categories = scores.get("categories") or {}
        category_html = "".join(
            f'<span><small>{esc(label)}</small><b>{esc(value)}</b></span>'
            for label, value in categories.items()
        )
        rows += f"""<a class="score-log-row" href="/episodes/{ep["date"]}.html">
  <time>{fmt_date(ep["date"])[0]}<small>{fmt_date(ep["date"])[1]}</small></time>
  <div><strong>{esc(scores["overall"])}</strong><span>{esc(scores.get("label") or ep["title"])}</span></div>
  <div class="category-scores">{category_html}</div><b>&#8599;</b>
</a>"""
    chart = "".join(
        f'<a href="/episodes/{ep["date"]}.html" style="height:{float(ep["scores"]["overall"]) * 10:.0f}%" title="{esc(ep["date"])} — {esc(ep["scores"]["overall"])}"><i></i></a>'
        for ep in history
    )
    body = f"""<div class="inner wrap score-history">
  <div class="page-intro"><p>THE COMPLETE LEDGER</p><h1>Every score.<br><em>Nothing erased.</em></h1><span>{len(history)} daily scores &middot; Updated with every episode</span></div>
  <div class="score-summary"><div><small>LATEST</small><strong>{esc(history[-1]["scores"]["overall"])}</strong><span>{esc(history[-1]["scores"].get("label"))}</span></div><div><small>ALL-TIME AVERAGE</small><strong>{average:.1f}</strong><span>Across {len(history)} episodes</span></div><div><small>HIGHEST</small><strong>{esc(peak["scores"]["overall"])}</strong><span>{fmt_date(peak["date"])[0]}</span></div></div>
  <section class="full-trend"><div><h2>Overall score</h2><p>Impact, novelty, and reach &middot; oldest to newest</p></div><div class="full-trend-chart">{chart}</div><div class="scale"><span>10</span><span>5</span><span>0</span></div></section>
  <div class="score-log"><div class="score-log-head"><span>DATE</span><span>OVERALL SIGNAL</span><span>CATEGORY BREAKDOWN</span></div>{rows}</div>
  <p class="ledger-note">This ledger is generated directly from the score attached to each published episode. The underlying structured record is available at <a href="/static/scores.json">/static/scores.json</a>.</p>
</div>"""
    return page("AI Score History — The Context Window", "Every Context Window AI Score, with the complete category breakdown and episode record.", "/scores/", body, active="scores")


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
        search = " ".join([ep.get("title", ""), ep.get("description", "")] + [t.get("title", "") for t in ep.get("topics", [])]).lower()
        rows += f"""<a class="episode-row" data-search="{esc(search)}" href="/episodes/{ep["date"]}.html">
  <time>{date_label}<small>{year}</small></time>
  <h3>{esc(ep["title"])}</h3>
  <span class="listen-icon">&#9654;</span><b>{dur}</b>
</a>"""
    return rows


def build_index(episodes: list[dict]) -> str:
    if not episodes:
        body = """<section class="hero wrap">
  <div class="eyebrow"><span class="live-dot"></span>LAUNCHING NOW</div>
  <h1>The most important<br>AI news. <em>Hosted by AIs.</em></h1>
  <div class="hero-bottom">
    <p class="dek">Claude and ChatGPT break down what changed in AI today, why it matters, and what comes next &mdash; every morning.</p>
    <div class="hosts"><span class="h-claude"><b></b>Claude &middot; Anthropic</span><span class="h-gpt"><b></b>ChatGPT &middot; OpenAI</span></div>
  </div>
</section>"""
        return page("The Context Window — AI news, hosted by AIs",
                    "Claude and ChatGPT break down the day's most important AI news. "
                    "A daily podcast on YouTube, Spotify, and Apple Podcasts.",
                    "/", body)
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

{briefing_snapshot(latest)}

{score_history_preview(episodes)}

{story_grid(latest)}

<section class="archive wrap">
  <div class="section-heading"><div><span>02</span><h2>Previous episodes</h2></div>
  <a href="/episodes/">View the archive <b>&#8599;</b></a></div>
  <div class="episode-list">{episode_rows(episodes, limit=6)}</div>
</section>"""
    return page("The Context Window — AI news, hosted by AIs",
                "Claude and ChatGPT break down the day's most important AI news. "
                "A daily podcast on YouTube, Spotify, and Apple Podcasts.",
                "/", body, og_image=youtube_image(latest))


def build_archive(episodes: list[dict]) -> str:
    body = f"""<div class="inner wrap">
  <div class="page-intro">
    <p>THE ARCHIVE</p>
    <h1>Every signal.<br><em>None of the noise.</em></h1>
    <span>{len(episodes)} episode{"s" if len(episodes) != 1 else ""} &middot; Updated every day</span>
  </div>
  <div class="archive-search"><label for="episode-search">SEARCH THE ARCHIVE</label><input id="episode-search" type="search" placeholder="OpenAI, safety, startups…" autocomplete="off"><span class="search-count">{len(episodes)} RESULTS</span></div>
  <div class="episode-list" style="margin-top:70px">{episode_rows(episodes)}</div>
</div>
<script>
(function(){{var input=document.getElementById('episode-search'),rows=[].slice.call(document.querySelectorAll('.episode-row')),count=document.querySelector('.search-count');input.oninput=function(){{var q=input.value.trim().toLowerCase(),shown=0;rows.forEach(function(row){{var yes=!q||row.dataset.search.indexOf(q)>-1;row.hidden=!yes;if(yes)shown++}});count.textContent=shown+' RESULT'+(shown===1?'':'S')}}}})();
</script>"""
    return page("Episodes — The Context Window", "Every episode of The Context Window.",
                "/episodes/", body, active="episodes")


def build_episode(ep: dict, ep_num: int) -> str | None:
    fragment_path = ROOT / "static" / "articles" / ep["article_file"]
    if not fragment_path.exists():
        return None
    fragment = fragment_path.read_text(encoding="utf-8")
    date_label, year, long_date = fmt_date(ep["date"])
    episode_url = f'{SITE_URL}/episodes/{ep["date"]}.html'
    schema = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": ep["title"],
        "description": ep.get("description", ""),
        "datePublished": ep["date"],
        "url": episode_url,
        "duration": f'PT{int(ep.get("duration_seconds") or 0)}S',
        "partOfSeries": {
            "@type": "PodcastSeries",
            "name": "The Context Window",
            "url": SITE_URL,
        },
    }
    if ep.get("podcast_url"):
        schema["associatedMedia"] = {
            "@type": "AudioObject",
            "contentUrl": ep["podcast_url"],
            "encodingFormat": "audio/mpeg",
        }
    schema_json = json.dumps(schema, ensure_ascii=False).replace("</", "<\\/")

    body = f"""<div class="inner wrap">
  <div class="episode-head">
    <p>EPISODE {ep_num} &middot; {long_date.upper()}, {year}</p>
    <h1>{esc(ep["title"])}</h1>
    <p class="standfirst">{esc(ep.get("description"))}</p>
    {audio_block(ep)}
    {platforms_row(ep)}
  </div>
  {briefing_snapshot(ep)}
  <div class="episode-tools"><span>{len(ep.get("topics") or [])} SOURCES &middot; FULL TRANSCRIPT</span><button class="share" data-event="Share episode" data-episode="{esc(ep["date"])}">SHARE THIS BRIEFING &#8599;</button></div>
  <article class="transcript">
{fragment}
  </article>
</div>
<script>
(function(){{var b=document.querySelector('.share');b.onclick=function(){{var d={{title:{json.dumps(ep["title"])},text:{json.dumps(ep.get("description", ""))},url:location.href}};if(navigator.share)navigator.share(d);else navigator.clipboard.writeText(location.href).then(function(){{b.textContent='LINK COPIED ✓'}})}}}})();
</script>"""
    return page(f'{ep["title"]} — The Context Window', ep.get("description", ""),
                f'/episodes/{ep["date"]}.html', body, active="episodes",
                og_image=youtube_image(ep), og_type="article",
                extra_head=f'<script type="application/ld+json">{schema_json}</script>')


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
      <p>That automation is part of the experiment, not a claim of infallibility.
      Every episode includes its source material and a complete transcript so
      listeners can inspect the reporting behind the conversation.</p>
    </div>
  </div>
  <div class="host-cards">
    <div class="host-card"><b style="background:#cc7832">C</b><h3>Claude</h3><small>Anthropic &middot; Host</small></div>
    <div class="host-card"><b style="background:#10a37f">C</b><h3>ChatGPT</h3><small>OpenAI &middot; Host</small></div>
    <div class="host-card"><b style="background:#4285f4">G</b><h3>Gemini</h3><small>Google &middot; Friday guest</small></div>
    <div class="host-card"><b style="background:#ef4444">G</b><h3>Grok</h3><small>xAI &middot; Friday guest</small></div>
  </div>
  <section class="methodology" id="methodology">
    <div class="section-heading"><div><span>01</span><h2>How it works</h2></div></div>
    <div class="method-grid">
      <article><span>01</span><h3>Discover</h3><p>The system gathers current AI reporting and removes duplicate or low-signal stories.</p></article>
      <article><span>02</span><h3>Research</h3><p>Candidate stories are checked against their source material before they reach the hosts.</p></article>
      <article><span>03</span><h3>Discuss</h3><p>The hosts explain the facts, challenge one another, and identify what changes for listeners.</p></article>
      <article><span>04</span><h3>Publish</h3><p>Audio, video, scores, sources, and transcripts are generated and distributed automatically.</p></article>
    </div>
    <div class="score-method">
      <div><p class="section-kicker">TODAY'S AI SCORE</p><h3>A daily measure of how consequential the news cycle is.</h3></div>
      <dl><div><dt>Impact</dt><dd>How meaningfully the development could change products, markets, policy, or research.</dd></div><div><dt>Novelty</dt><dd>Whether the development adds genuinely new information rather than repeating an existing narrative.</dd></div><div><dt>Reach</dt><dd>How broadly the consequences may extend across people, companies, and institutions.</dd></div></dl>
    </div>
    <div class="standards"><h3>Editorial standard</h3><p>Clear sourcing. No invented certainty. Distinguish reported facts from host interpretation. Preserve disagreements when they illuminate the story. Because the system is fully automated, errors in source reporting or model interpretation remain possible; the linked sources are the record readers should use to verify consequential claims.</p></div>
  </section>
</div>"""
    return page("About — The Context Window",
                "The first daily news show produced and hosted entirely by AI.",
                "/about.html", body, active="about")


def build_callback() -> str:
    body = """<div class="inner wrap"><div class="page-intro">
  <p>AUTHORIZATION COMPLETE</p>
  <h1>You can close<br><em>this tab.</em></h1>
  <span>Copy the full URL from the address bar back into the token script.</span>
</div></div>"""
    return page("TikTok authorization — The Context Window", "OAuth redirect landing page.",
                "/tiktok-callback", body)


def main() -> None:
    articles_path = ROOT / "static" / "articles.json"
    episodes = json.loads(articles_path.read_text(encoding="utf-8"))
    episodes.sort(key=lambda e: e["date"], reverse=True)
    if not episodes:
        raise SystemExit("articles.json is empty — nothing to build")

    (ROOT / "episodes").mkdir(exist_ok=True)
    (ROOT / "scores").mkdir(exist_ok=True)

    (ROOT / "index.html").write_text(build_index(episodes), encoding="utf-8")
    (ROOT / "episodes" / "index.html").write_text(build_archive(episodes), encoding="utf-8")
    (ROOT / "scores" / "index.html").write_text(build_scores(episodes), encoding="utf-8")
    (ROOT / "about.html").write_text(build_about(episodes), encoding="utf-8")
    (ROOT / "tiktok-callback.html").write_text(build_callback(), encoding="utf-8")
    score_log = [
        {
            "date": ep["date"],
            "episode": f'/episodes/{ep["date"]}.html',
            "title": ep["title"],
            "overall": ep["scores"]["overall"],
            "label": ep["scores"].get("label"),
            "categories": ep["scores"].get("categories") or {},
        }
        for ep in scored_episodes(episodes)
    ]
    (ROOT / "static" / "scores.json").write_text(
        json.dumps(score_log, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sitemap_urls = [
        (f"{SITE_URL}/", episodes[0]["date"]),
        (f"{SITE_URL}/episodes/", episodes[0]["date"]),
        (f"{SITE_URL}/scores/", episodes[0]["date"]),
        (f"{SITE_URL}/about.html", episodes[0]["date"]),
    ] + [
        (f'{SITE_URL}/episodes/{ep["date"]}.html', ep["date"])
        for ep in episodes
    ]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap.extend(
        f"  <url><loc>{html.escape(url)}</loc><lastmod>{date}</lastmod></url>"
        for url, date in sitemap_urls
    )
    sitemap.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n",
        encoding="utf-8",
    )

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
