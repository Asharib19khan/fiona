import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

/**
 * R1 import boundaries for the shared UI package: it may use @fiona/contracts,
 * but never apps or services. test/boundaries.test.ts proves each pattern fires.
 */
const boundaryPatterns = [
  {
    regex: "(^|/)apps(/|$)|^@fiona/(web|mobile)(/|$)",
    message: "R1: packages/ui must not import from apps.",
  },
  {
    regex: "(^|/)services(/|$)|^@fiona/(engine|agents|guardian)(/|$)",
    message: "R1: packages/ui must not import from services.",
  },
];

export default defineConfig([
  { ignores: ["dist/**"] },
  tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx,mjs}"],
    rules: {
      "no-restricted-imports": ["error", { patterns: boundaryPatterns }],
    },
  },
]);
