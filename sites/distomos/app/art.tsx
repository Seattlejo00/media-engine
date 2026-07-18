"use client";

import { useState } from "react";

const artworks = [
  { file: "/landsat-kevir.jpg", title: "KEVIR DESERT, IRAN", satellite: "LANDSAT 8", coordinates: ["30.95° N", "54.48° E"] },
  { file: "/earth-art/desert-ribbons.jpg", title: "DESERT RIBBONS, MOROCCO", satellite: "LANDSAT 8", coordinates: ["28.14° N", "10.63° W"] },
  { file: "/earth-art/painting-the-desert.jpg", title: "LAKE EYRE BASIN, AUSTRALIA", satellite: "LANDSAT 8", coordinates: ["25.39° S", "140.57° E"] },
  { file: "/earth-art/rock-folding.jpg", title: "LABRADOR TROUGH, CANADA", satellite: "LANDSAT 8", coordinates: ["55.73° N", "67.52° W"] },
];

function dailyIndex() {
  const now = new Date();
  const start = Date.UTC(now.getUTCFullYear(), 0, 0);
  return Math.floor((Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - start) / 86400000) % artworks.length;
}

export function DailyArtwork() {
  const [index] = useState(dailyIndex);
  const art = artworks[index];
  return <>
    <div className="hero-image" style={{ backgroundImage: `url('${art.file}')` }} />
    <div className="image-credit">{art.satellite} · {art.title} <span>USGS / NASA</span></div>
    <div className="coordinate">{art.coordinates[0]}<br />{art.coordinates[1]}</div>
  </>;
}
