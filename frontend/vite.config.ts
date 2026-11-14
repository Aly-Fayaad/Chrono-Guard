import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ["chrono-guard-2b4i.vercel.app"],
  },
  preview: {
    allowedHosts: ["chrono-guard-2b4i.vercel.app"],
  },
});