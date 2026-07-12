export function BriefingPlayer({ href, hasAudio }: { href: string; hasAudio: boolean }) {
  return <a className="player" href={href} target="_blank" rel="noopener noreferrer" aria-label="Open the latest AI Daily episode">
    <span className="play">▶</span>
    <div><span>{hasAudio ? "LISTEN TO THE EPISODE" : "WATCH THE EPISODE"}</span><span>OPEN ↗</span><i><b style={{width:"100%"}}/></i></div>
    <small>↗</small>
  </a>;
}
