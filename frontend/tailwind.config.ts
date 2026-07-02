import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0A0E1A",
        panel: "#111726",
        line: "#1E2638",
        accent: "#3B82F6",
        pos: "#10B981",
        neg: "#EF4444",
        warn: "#F59E0B",
      },
    },
  },
  plugins: [],
};
export default config;
