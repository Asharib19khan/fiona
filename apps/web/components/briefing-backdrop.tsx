"use client";

import dynamic from "next/dynamic";

// WebGL, so it renders in the browser only.
const GradientASCII = dynamic(() => import("./vendor/gradient-ascii/GradientASCII"), { ssr: false });

/**
 * A quiet, moving wash of light behind the top of the briefing (React Bits GradientASCII in
 * light mode, in the workspace blues). It sits behind the content, fades out at the edges,
 * and never takes clicks.
 */
export function BriefingBackdrop() {
  return (
    <div className="briefing-backdrop" aria-hidden="true">
      <GradientASCII
        lightMode
        shape="horizon"
        colors={["#5a9ff0", "#8dbcf2", "#c3dbf6", "#e8f1fb"]}
        characters=" .:-=+x*#"
        cellSize={15}
        density={0.7}
        glyphOpacity={0.6}
        gradientOpacity={0.4}
        glow={0.12}
        flicker={0.15}
        softness={0.7}
        flow={0.4}
        speed={0.6}
        grain={0.03}
        scrambleRadius={0.08}
        clickEffect="none"
      />
    </div>
  );
}
