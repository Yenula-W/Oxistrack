import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0B0D",
        surface: { DEFAULT: "#111114", 2: "#17171B", 3: "#1E1E23" },
        line: { DEFAULT: "#26262B", strong: "#323238" },
        ink: { DEFAULT: "#EDEDEF", 2: "#A6A6AE", 3: "#76767F" },
        brand: { DEFAULT: "#EDEDEF", strong: "#FFFFFF", soft: "#FFFFFF14", text: "#EDEDEF" },
        ok: { DEFAULT: "#2FBF8A", soft: "#2FBF8A1f" },
        warn: { DEFAULT: "#F0A63A", soft: "#F0A63A1f" },
        bad: { DEFAULT: "#F0616D", soft: "#F0616D1f" },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        heading: ["Plus Jakarta Sans", "var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      borderRadius: { xl: "0.875rem", "2xl": "1.125rem" },
      boxShadow: { pop: "0 12px 32px -12px rgba(0,0,0,.7)" },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "pop-in": { from: { opacity: "0", transform: "translate(-50%,-48%) scale(.97)" }, to: { opacity: "1", transform: "translate(-50%,-50%) scale(1)" } },
        "slide-in": { from: { opacity: "0", transform: "translateX(16px)" }, to: { opacity: "1", transform: "translateX(0)" } },
      },
      animation: { "fade-in": "fade-in .15s ease-out", "pop-in": "pop-in .18s ease-out", "slide-in": "slide-in .2s ease-out" },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
