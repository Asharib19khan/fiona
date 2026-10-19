import type { CSSProperties, HTMLAttributes, ReactElement } from "react";

/** Types for the React Bits GradientASCII component (GradientASCII.jsx, copied in unchanged). */
export interface GradientASCIIProps extends Omit<HTMLAttributes<HTMLDivElement>, "style"> {
  colors?: string[];
  shape?: "horizon" | "pinch" | "rise" | "eclipse";
  characters?: string;
  cellSize?: number;
  density?: number;
  glyphOpacity?: number;
  glow?: number;
  depthOfField?: number;
  flicker?: number;
  softness?: number;
  scale?: number;
  flow?: number;
  speed?: number;
  gradientOpacity?: number;
  grain?: number;
  variation?: number;
  mouseInteraction?: boolean;
  scrambleRadius?: number;
  clickEffect?: "wave" | "burst" | "none";
  intro?: boolean;
  lightMode?: boolean;
  fontFamily?: string;
  dpr?: number;
  className?: string;
  style?: CSSProperties;
}

declare function GradientASCII(props: GradientASCIIProps): ReactElement;
export default GradientASCII;
