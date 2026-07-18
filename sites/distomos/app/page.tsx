import { DailyArtwork } from "./art";
import { LatestBriefing } from "./signal";
import latest from "./latest-episode.json";

const contextWindowUrl = process.env.NEXT_PUBLIC_CONTEXT_WINDOW_URL || "https://contextwindow.distomostech.com";
const spotifyUrl = "https://open.spotify.com/show/033OoZlyZBlEwCd6kmNdpT";
const youtubeUrl = "https://www.youtube.com/@TheContextWindow-q1z";

export default function Home() {
  return <main>
    <section className="hero" id="top">
      <DailyArtwork />
      <div className="hero-shade" />
      <header>
        <a className="wordmark" href="#top" aria-label="Distomos home"><i>D</i><span>DISTOMOS</span></a>
        <nav><a href="#context-window">The Context Window</a><a href="#about">About</a></nav>
        <a className="nav-cta" href="#context-window">Start here <b>↗</b></a>
      </header>
      <div className="hero-copy">
        <p className="overline"><span /> THE CONTEXT WINDOW BY DISTOMOS</p>
        <h1>See the shape<br />of what’s <em>next.</em></h1>
        <div className="hero-foot"><p>Distomos publishes The Context Window—the essential briefing on what changed and why it matters.</p><a href="#context-window">Start with The Context Window <b>↘</b></a></div>
      </div>
    </section>

    <section className="manifesto shell" id="about">
      <p className="index">00 / WHY WE EXIST</p>
      <div><h2>AI changes every day.<br /><em>Understanding it shouldn’t take all day.</em></h2><p>Distomos publishes The Context Window for people who want to understand artificial intelligence without living inside the news cycle. We read the noise, find the signal, and deliver the essential context every morning.</p></div>
    </section>

    <section className="daily shell" id="context-window">
      <div className="daily-intro">
        <p className="index">01 / THE DAILY SIGNAL</p>
        <div className="daily-lockup"><i /> <span>THE CONTEXT WINDOW<small>BY DISTOMOS</small></span></div>
        <h2>The most important AI news.<br /><em>Every morning.</em></h2>
        <p>An eight-minute briefing on what changed, why it matters, and what comes next. No hype. Just signal.</p>
        <div className="daily-actions">
          <a className="text-link" href={contextWindowUrl} target="_blank">Explore The Context Window <b>↗</b></a>
          <a className="text-link" href={spotifyUrl} target="_blank" rel="noopener noreferrer">Listen on Spotify <b>↗</b></a>
          <a className="text-link" href={youtubeUrl} target="_blank" rel="noopener noreferrer">Watch on YouTube <b>↗</b></a>
        </div>
      </div>
      <LatestBriefing fallback={latest} feedUrl={`${contextWindowUrl}/static/articles.json`} />
    </section>

    <section className="methodology shell" id="methodology">
      <div>
        <p className="index">02 / HOW IT WORKS</p>
        <h2>Fully automated.<br /><em>Radically transparent.</em></h2>
      </div>
      <ol>
        <li><span>01</span><div><h3>Discover</h3><p>The system scans current AI reporting and ranks stories by impact, novelty, and reach.</p></div></li>
        <li><span>02</span><div><h3>Interrogate</h3><p>AI hosts examine the strongest claims, disagree where useful, and connect the day’s events to the larger picture.</p></div></li>
        <li><span>03</span><div><h3>Publish</h3><p>Audio, video, sources, scores, and transcripts are produced and distributed without a human in the publishing loop.</p></div></li>
      </ol>
      <p className="automation-note">Automation is the format, not a claim of infallibility. Every briefing preserves its sources so readers can inspect the reporting behind it.</p>
    </section>

    <section className="art-break"><div /><p>Patterns appear<br />before predictions.</p><small>EARTH AS ART · USGS / NASA LANDSAT</small></section>

    <footer className="shell"><div className="wordmark"><i>D</i><span>DISTOMOS</span></div><p>Publisher of The Context Window.<br />Signal over noise, every morning.</p><nav><a href={contextWindowUrl} target="_blank">The Context Window</a><a href={spotifyUrl} target="_blank" rel="noopener noreferrer">Spotify</a><a href={youtubeUrl} target="_blank" rel="noopener noreferrer">YouTube</a><a href="#about">About</a></nav><div className="footer-bottom"><span>© 2026 DISTOMOS</span><span>EARTH IMAGERY: USGS / NASA LANDSAT</span><span>DENVER, COLORADO</span></div></footer>
  </main>;
}
