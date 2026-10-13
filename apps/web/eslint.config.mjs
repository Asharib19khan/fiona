import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * R1 import boundaries for the Window. It imports workspace code only from
 * @fiona/contracts and @fiona/ui, and it reaches services over HTTP through the BFF,
 * never by import. test/boundaries.test.ts proves each pattern fires.
 */
const boundaryPatterns = [
  {
    regex: "(^|/)services(/|$)|^@fiona/(engine|agents|guardian)(/|$)",
    message: "R1: the Window reaches services over HTTP through the BFF (/api/fiona/*), never by import.",
  },
  {
    regex: "(^|/)packages/",
    message: "R1: import shared code as @fiona/contracts or @fiona/ui, not by relative path.",
  },
  {
    regex: "^@fiona/(?!(contracts|ui|engine|agents|guardian)(/|$))",
    message: "R1: apps/web may import only @fiona/contracts and @fiona/ui from the workspace.",
  },
];

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{ts,tsx,js,jsx,mjs}"],
    rules: {
      "no-restricted-imports": ["error", { patterns: boundaryPatterns }],
    },
  },
  globalIgnores([".next/**", "out/**", "next-env.d.ts"]),
]);
