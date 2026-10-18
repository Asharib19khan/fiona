"use client";

import { useEffect, useState } from "react";

export function BootScreen({ onComplete }: { onComplete?: () => void }) {
  const [fading, setFading] = useState(false);
  // Plays once per browser session: hidden until the client checks it has not been seen.
  const [removed, setRemoved] = useState(true);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      try {
        if (window.sessionStorage.getItem("fiona:intro-seen")) return;
        window.sessionStorage.setItem("fiona:intro-seen", "1");
      } catch {
        return; // storage blocked: skip the intro rather than replay it on every page
      }
      setRemoved(false);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    // Allow replaying the intro anytime by dispatching 'fiona:replay-intro'
    function handleReplay() {
      setRemoved(false);
      setFading(false);
    }
    window.addEventListener("fiona:replay-intro", handleReplay);
    return () => window.removeEventListener("fiona:replay-intro", handleReplay);
  }, []);

  useEffect(() => {
    if (removed) return;

    // 0.0s - 0.7s: Staggered letter reveal (F - I - O - N - A)
    // 0.7s - 2.4s: Liquid light shimmer sweep across all letters
    // 2.6s: Elegant liquid fade-out begins (scale + blur dissolve)
    // 3.2s: Cleanly unmount from DOM
    const fadeTimer = setTimeout(() => {
      setFading(true);
    }, 2600);

    const removeTimer = setTimeout(() => {
      setRemoved(true);
      onComplete?.();
    }, 3200);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, [removed, onComplete]);

  if (removed) return null;

  function dismiss() {
    setFading(true);
    setTimeout(() => {
      setRemoved(true);
      onComplete?.();
    }, 450);
  }

  return (
    <div
      className={`fiona-intro-overlay ${fading ? "fiona-intro-fade" : ""}`}
      onClick={dismiss}
      role="dialog"
      aria-modal="true"
      aria-label="Fiona Loading"
    >
      {/* Pure serene backdrop with soft diffuse ambient warmth */}
      <div className="fiona-intro-backdrop" />
      <div className="fiona-intro-glow" />

      {/* The Centerpiece: EXCLUSIVELY the wordmark "FIONA", beautifully animated */}
      <div className="fiona-wordmark-container">
        <div className="fiona-wordmark">
          <span className="fiona-letter fiona-l-1">F</span>
          <span className="fiona-letter fiona-l-2">I</span>
          <span className="fiona-letter fiona-l-3">O</span>
          <span className="fiona-letter fiona-l-4">N</span>
          <span className="fiona-letter fiona-l-5">A</span>
        </div>
      </div>
    </div>
  );
}
