import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on :8000; in production nginx serves both from one origin.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: process.env.VIBELENS_API ?? "http://localhost:8000", changeOrigin: true } } },
});
