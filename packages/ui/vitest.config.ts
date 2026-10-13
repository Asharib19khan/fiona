import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"],
    testTimeout: 30_000,
  },
});
