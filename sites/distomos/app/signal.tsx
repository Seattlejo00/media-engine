export function BriefingPlayer({ href, hasAudio }: { href: string; hasAudio: boolean }) {
  return <a className="player" href={href} target="_blank" rel="noopener noreferrer" aria-label="Open the latest The Context Window episode">
    <span className="play">▶</span>
    <div>
      <span>{hasAudio ? "LISTEN TO THE EPISODE" : "WATCH THE EPISODE"}</span>
      <small>{hasAudio ? "LATEST BRIEFING" : "ON YOUTUBE"}</small>
    </div>
    <b aria-hidden="true">↗</b>
  </a>;
}
