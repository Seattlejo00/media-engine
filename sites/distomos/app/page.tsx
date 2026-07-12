import { BriefingPlayer } from "./signal";

export default function Home() {
  return <main>
    <section className="hero" id="top">
      <div className="hero-image" />
      <div className="hero-shade" />
      <header>
        <a className="wordmark" href="#top" aria-label="Distomos home"><i>D</i><span>DISTOMOS</span></a>
        <nav><a href="#ai-daily">AI Daily</a><a href="#about">About</a></nav>
        <a className="nav-cta" href="#ai-daily">Start here <b>↗</b></a>
      </header>
      <div className="hero-copy">
        <p className="overline"><span /> AI DAILY BY DISTOMOS</p>
        <h1>See the shape<br />of what’s <em>next.</em></h1>
        <div className="hero-foot"><p>Distomos publishes AI Daily—the essential eight-minute briefing on what changed and why it matters.</p><a href="#ai-daily">Start with AI Daily <b>↘</b></a></div>
      </div>
      <div className="image-credit">LANDSAT 8 · KEVIR DESERT, IRAN <span>USGS / NASA</span></div>
      <div className="coordinate">30.95° N<br />54.48° E</div>
    </section>

    <section className="manifesto shell" id="about">
      <p className="index">00 / WHY WE EXIST</p>
      <div><h2>AI changes every day.<br /><em>Understanding it shouldn’t take all day.</em></h2><p>Distomos publishes AI Daily for people who want to understand artificial intelligence without living inside the news cycle. We read the noise, find the signal, and deliver the essential context every weekday morning.</p></div>
    </section>

    <section className="daily shell" id="ai-daily">
      <div className="daily-intro">
        <p className="index">01 / THE DAILY SIGNAL</p>
        <div className="daily-lockup"><i /> <span>AI DAILY<small>BY DISTOMOS</small></span></div>
        <h2>The most important AI news.<br /><em>Every morning.</em></h2>
        <p>An eight-minute briefing on what changed, why it matters, and what comes next. No hype. Just signal.</p>
        <a className="text-link" href="https://theaidaily.distomostech.com" target="_blank">Explore AI Daily <b>↗</b></a>
      </div>
      <div className="daily-card">
        <div className="card-top"><span><i /> TODAY’S BRIEFING</span><time>JUL 11 · 08:12</time></div>
        <h3>OpenAI’s agent play, Claude’s enterprise push, and a robotics breakthrough</h3>
        <BriefingPlayer />
        <div className="today-score"><div><span>TODAY’S AI SCORE</span><strong>8.7</strong><small>/ 10</small></div><p>High signal day</p></div>
        <div className="score-bars">{[["OpenAI",94],["Anthropic",87],["Research",73],["Startups",69]].map(([x,v])=><div key={String(x)}><span>{x}</span><i><b style={{width:`${v}%`}} /></i><strong>{Number(v)/10}</strong></div>)}</div>
      </div>
    </section>

    <section className="art-break"><div /><p>Patterns appear<br />before predictions.</p><small>KEVIR DESERT · LANDSAT 8</small></section>

    <footer className="shell"><div className="wordmark"><i>D</i><span>DISTOMOS</span></div><p>Publisher of AI Daily.<br />Signal over noise, every morning.</p><nav><a href="#ai-daily">AI Daily</a><a href="#about">About</a><a href="mailto:hello@distomos.com">Contact</a></nav><div className="footer-bottom"><span>© 2026 DISTOMOS</span><span>EARTH IMAGERY: USGS / NASA LANDSAT</span><span>DENVER, COLORADO</span></div></footer>
  </main>;
}
