import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ["sb-1er6spx1lxbq.vercel.run"],
  },
  preview: {
    allowedHosts: ["sb-1er6spx1lxbq.vercel.run"],
  }
});