import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: { background: "#0b0f14", panel: "#111827", panelborder: "#1f2937",
                 accent: "#22c55e", danger: "#ef4444", warn: "#f59e0b" },
    },
  },
  plugins: [],
};

export default config;
