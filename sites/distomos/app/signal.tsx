"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Topic = { title?: string; source?: string; url?: string; category?: string };
type Scores = {
  overall?: number;
  label?: string;
  categories?: Record<string, number>;
};
export type Episode = {
  date: string;
  title: string;
  description?: string;
  youtube_url?: string | null;
  podcast_url?: string | null;
  duration_seconds?: number | null;
  scores?: Scores | null;
  topics?: Topic[];
};

declare global {
  interface Window {
    va?: (event: string, payload: Record<string, unknown>) => void;
  }
}

function track(name: string, data: Record<string, unknown> = {}) {
  window.va?.("event", { name, data });
}

function formatTime(value: number) {
  if (!Number.isFinite(value)) return "00:00";
  const total = Math.max(0, Math.floor(value));
  return `${Math.floor(total / 60).toString().padStart(2, "0")}:${(total % 60).toString().padStart(2, "0")}`;
}

function formatDate(date: string) {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  }).toUpperCase();
}

function AudioPlayer({ episode }: { episode: Episode }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const playerRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(episode.duration_seconds || 0);
  const [speed, setSpeed] = useState(1);
  const [offscreen, setOffscreen] = useState(false);

  useEffect(() => {
    if (!playerRef.current || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(([entry]) => setOffscreen(!entry.isIntersecting), { threshold: 0.2 });
    observer.observe(playerRef.current);
    return () => observer.disconnect();
  }, []);

  const toggle = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      await audio.play();
      track("Episode play", { episode: episode.date, surface: "Distomos" });
    } else {
      audio.pause();
    }
  };

  const changeSpeed = () => {
    const speeds = [1, 1.25, 1.5, 2];
    const next = speeds[(speeds.indexOf(speed) + 1) % speeds.length];
    setSpeed(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
    track("Playback speed", { speed: next, episode: episode.date });
  };

  const controls = (compact = false) => <>
    <button className="play" onClick={toggle} aria-label={playing ? "Pause episode" : "Play episode"}>{playing ? "Ⅱ" : "▶"}</button>
    <div className="player-body">
      <div className="player-label"><span>{compact ? episode.title : playing ? "PLAYING THE LATEST BRIEFING" : "LISTEN TO THE EPISODE"}</span><small>{formatTime(current)} / {formatTime(duration)}</small></div>
      {!compact && <input aria-label="Episode progress" type="range" min="0" max={duration || 1} step="1" value={current} onChange={(event) => {
        const next = Number(event.target.value);
        if (audioRef.current) audioRef.current.currentTime = next;
        setCurrent(next);
      }} />}
    </div>
    <button className="speed" onClick={changeSpeed} aria-label={`Playback speed ${speed} times`}>{speed}×</button>
  </>;

  return <>
    <div className="player" ref={playerRef}>
      <audio ref={audioRef} src={episode.podcast_url || undefined} preload="metadata" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)} onEnded={() => setPlaying(false)} />
      {controls()}
    </div>
    {playing && offscreen && <div className="mini-player" role="region" aria-label="Now playing">{controls(true)}</div>}
  </>;
}

function Score({ scores }: { scores?: Scores | null }) {
  if (!scores?.overall) return null;
  return <div className="today-score">
    <div><span>TODAY&apos;S AI SCORE</span><strong>{scores.overall}</strong><small> / 10</small></div>
    <p>{scores.label}</p>
    <div className="score-actions"><a href="https://contextwindow.distomostech.com/scores/" target="_blank" rel="noopener noreferrer">VIEW SCORE HISTORY ↗</a><a href="https://contextwindow.distomostech.com/about.html#methodology" target="_blank" rel="noopener noreferrer">METHODOLOGY ↗</a></div>
  </div>;
}

export function LatestBriefing({ fallback, feedUrl }: { fallback: Episode; feedUrl: string }) {
  const [episode, setEpisode] = useState(fallback);

  useEffect(() => {
    fetch(feedUrl, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Feed unavailable")))
      .then((episodes: Episode[]) => episodes[0] && setEpisode(episodes[0]))
      .catch(() => undefined);
  }, [feedUrl]);

  const topics = useMemo(() => (episode.topics || []).filter((topic) => topic.title).slice(0, 3), [episode]);
  const destination = `https://contextwindow.distomostech.com/episodes/${episode.date}.html`;

  return <div className="daily-card">
    <div className="card-top"><span><i /> LATEST EPISODE</span><time>{formatDate(episode.date)}</time></div>
    <h3>{episode.title}</h3>
    {episode.podcast_url ? <AudioPlayer episode={episode} /> : <a className="player player-link" href={episode.youtube_url || destination} target="_blank" rel="noopener noreferrer"><span className="play">▶</span><div className="player-body"><span>WATCH THE EPISODE</span><small>ON YOUTUBE</small></div><b>↗</b></a>}
    {topics.length > 0 && <div className="briefing-glance">
      <span>THREE THINGS TO KNOW</span>
      <ol>{topics.map((topic, index) => <li key={`${topic.title}-${index}`}><b>0{index + 1}</b><span>{topic.title}</span></li>)}</ol>
      {episode.description && <p><b>WHY IT MATTERS</b>{episode.description}</p>}
      <a href={destination} target="_blank" rel="noopener noreferrer" onClick={() => track("Open briefing", { episode: episode.date })}>READ THE FULL BRIEFING ↗</a>
    </div>}
    <Score scores={episode.scores} />
  </div>;
}
