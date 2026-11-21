/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.CREWMIND_API ?? "http://127.0.0.1:8433";
const proxy = Object.fromEntries(
  ["/v1", "/files", "/stream", "/healthz"].map((path) => [path, { target: api, changeOrigin: false }]),
);

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
