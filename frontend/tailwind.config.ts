import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#05070d",
          900: "#0a0e17",
          850: "#0e1420",
          800: "#131a29",
          700: "#1c2436",
          600: "#2a3446",
        },
        ember: {
          300: "#ffd29d",
          400: "#ffb54d",
          500: "#f59e0b",
          600: "#c47a06",
        },
        volt: {
          300: "#8fe8ff",
          400: "#38d2ff",
          500: "#00b4e0",
          600: "#0a8fb5",
        },
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "'Liberation Mono'",
          "monospace",
        ],
      },
      boxShadow: {
        glow: "0 0 24px -6px rgba(245, 158, 11, 0.35)",
        "glow-cyan": "0 0 24px -6px rgba(56, 210, 255, 0.35)",
        panel: "0 8px 32px -12px rgba(0, 0, 0, 0.7)",
      },
      keyframes: {
        pulseDot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.25" },
        },
        scanline: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
      animation: {
        pulseDot: "pulseDot 1.6s ease-in-out infinite",
        scanline: "scanline 6s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;