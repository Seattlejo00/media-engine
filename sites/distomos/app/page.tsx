import { BriefingPlayer } from "./signal";
import latest from "./latest-episode.json";

const latestDate = new Date(`${latest.date}T12:00:00Z`).toLocaleDateString("en-US", {
  month: "short",
  day: "2-digit",
  timeZone: "UTC",
}).toUpperCase();
const aiDailyUrl = process.env.NEXT_PUBLIC_AI_DAILY_URL || "https://contextwindow.distomostech.com";
const latestHref = latest.podcast_url || latest.youtube_url || aiDailyUrl;

export default function Home() {
  return <main>
    <section className="hero" id="top">
      <div className="hero-image" />
      <div className="hero-shade" />
      <header>
        <a className="wordmark" href="#top" aria-label="Distomos home"><i>D</i><span>DISTOMOS</span></a>
        <nav><a href="#ai-daily">The Context Window</a><a href="#about">About</a></nav>
        <a className="nav-cta" href="#ai-daily">Start here <b>↗</b></a>
      </header>
      <div className="hero-copy">
        <p className="overline"><span /> THE CONTEXT WINDOW BY DISTOMOS</p>
        <h1>See the shape<br />of what’s <em>next.</em></h1>
        <div className="hero-foot"><p>Distomos publishes The Context Window—the essential eight-minute briefing on what changed and why it matters.</p><a href="#ai-daily">Start with The Context Window <b>↘</b></a></div>
      </div>
      <div className="image-credit">LANDSAT 8 · KEVIR DESERT, IRAN <span>USGS / NASA</span></div>
      <div className="coordinate">30.95° N<br />54.48° E</div>
    </section>

    <section className="manifesto shell" id="about">
      <p className="index">00 / WHY WE EXIST</p>
      <div><h2>AI changes every day.<br /><em>Understanding it shouldn’t take all day.</em></h2><p>Distomos publishes The Context Window for people who want to understand artificial intelligence without living inside the news cycle. We read the noise, find the signal, and deliver the essential context every weekday morning.</p></div>
    </section>

    <section className="daily shell" id="ai-daily">
      <div className="daily-intro">
        <p className="index">01 / THE DAILY SIGNAL</p>
        <div className="daily-lockup"><i /> <span>THE CONTEXT WINDOW<small>BY DISTOMOS</small></span></div>
        <h2>The most important AI news.<br /><em>Every morning.</em></h2>
        <p>An eight-minute briefing on what changed, why it matters, and what comes next. No hype. Just signal.</p>
        <a className="text-link" href={aiDailyUrl} target="_blank">Explore The Context Window <b>↗</b></a>
      </div>
      <div className="daily-card">
        <div className="card-top"><span><i /> LATEST EPISODE</span><time>{latestDate}</time></div>
        <h3>{latest.title}</h3>
        <BriefingPlayer href={latestHref} hasAudio={Boolean(latest.podcast_url)} />
      </div>
    </section>

    <section className="art-break"><div /><p>Patterns appear<br />before predictions.</p><small>KEVIR DESERT · LANDSAT 8</small></section>

    <footer className="shell"><div className="wordmark"><i>D</i><span>DISTOMOS</span></div><p>Publisher of The Context Window.<br />Signal over noise, every morning.</p><nav><a href={aiDailyUrl} target="_blank">The Context Window</a><a href="#about">About</a><a href={latestHref} target="_blank">Latest episode</a></nav><div className="footer-bottom"><span>© 2026 DISTOMOS</span><span>EARTH IMAGERY: USGS / NASA LANDSAT</span><span>DENVER, COLORADO</span></div></footer>
  </main>;
}
