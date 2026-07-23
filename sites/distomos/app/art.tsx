"use client";

import { useEffect, useState } from "react";

const artworks = [
  { file: "/landsat-kevir.jpg", title: "KEVIR DESERT, IRAN", satellite: "LANDSAT 8", coordinates: ["30.95° N", "54.48° E"], palette: { accent: "#5ce5ec", accentRgb: "92 229 236", paper: "#e8e2d5", paperHover: "#f1ecdf" } },
  { file: "/earth-art/desert-ribbons.jpg", title: "DESERT RIBBONS, MOROCCO", satellite: "LANDSAT 8", coordinates: ["28.14° N", "10.63° W"], palette: { accent: "#f07eb5", accentRgb: "240 126 181", paper: "#eee1dc", paperHover: "#f7eae5" } },
  { file: "/earth-art/painting-the-desert.jpg", title: "LAKE EYRE BASIN, AUSTRALIA", satellite: "LANDSAT 8", coordinates: ["25.39° S", "140.57° E"], palette: { accent: "#64b5ff", accentRgb: "100 181 255", paper: "#e2e6e8", paperHover: "#edf1f3" } },
  { file: "/earth-art/rock-folding.jpg", title: "LABRADOR TROUGH, CANADA", satellite: "LANDSAT 8", coordinates: ["55.73° N", "67.52° W"], palette: { accent: "#f0aa4f", accentRgb: "240 170 79", paper: "#ebe0d0", paperHover: "#f5eadb" } },
];

const rotationMs = 2 * 60 * 60 * 1000;

function currentArtworkIndex() {
  return Math.floor(Date.now() / rotationMs) % artworks.length;
}

export function DailyArtwork() {
  const [index, setIndex] = useState(currentArtworkIndex);
  const art = artworks[index];

  useEffect(() => {
    let timer: number;
    const scheduleNextRotation = () => {
      const delay = rotationMs - (Date.now() % rotationMs) + 250;
      timer = window.setTimeout(() => {
        setIndex(currentArtworkIndex());
        scheduleNextRotation();
      }, delay);
    };

    scheduleNextRotation();
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const properties = {
      "--blue": art.palette.accent,
      "--accent-rgb": art.palette.accentRgb,
      "--paper": art.palette.paper,
      "--paper-hover": art.palette.paperHover,
    };

    Object.entries(properties).forEach(([property, value]) => root.style.setProperty(property, value));
    root.dataset.artPalette = art.title.toLowerCase().replaceAll(" ", "-");

    return () => {
      Object.keys(properties).forEach((property) => root.style.removeProperty(property));
      delete root.dataset.artPalette;
    };
  }, [art]);

  return <>
    <div className="hero-image" style={{ backgroundImage: `url('${art.file}')` }} />
    <div className="image-credit">{art.satellite} · {art.title} <span>USGS / NASA</span></div>
    <div className="coordinate">{art.coordinates[0]}<br />{art.coordinates[1]}</div>
  </>;
}
