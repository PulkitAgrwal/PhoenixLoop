import type { Config } from "tailwindcss";

const palette = {
  canvas: "#101010",
  "canvas-soft": "#1a1a1a",
  "canvas-text-soft": "#f5f6f7",
  hairline: "#3d3a39",
  "hairline-soft": "#b8b3b0",
  ink: "#f2f2f2",
  "ink-strong": "#ffffff",
  body: "#bdbdbd",
  mute: "#8b949e",
  brand: "#00d992",
  "brand-soft": "#2fd6a1",
  "brand-deep": "#10b981",
  "on-brand": "#101010",
  fail: "#e35858",
  warn: "#e6b450",
};

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1.25rem", lg: "2rem" },
      screens: { "2xl": "1280px" },
    },
    extend: {
      colors: {
        ...palette,
        border: palette.hairline,
        input: palette.hairline,
        ring: palette.brand,
        background: palette.canvas,
        foreground: palette.ink,
        primary: { DEFAULT: palette.brand, foreground: palette["on-brand"] },
        secondary: { DEFAULT: palette["canvas-soft"], foreground: palette.ink },
        destructive: { DEFAULT: palette.fail, foreground: palette["ink-strong"] },
        muted: { DEFAULT: palette["canvas-soft"], foreground: palette.body },
        accent: { DEFAULT: palette["canvas-soft"], foreground: palette.ink },
        popover: { DEFAULT: palette.canvas, foreground: palette.ink },
        card: { DEFAULT: palette.canvas, foreground: palette.ink },
      },
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      fontSize: {
        "display-xl": ["60px", { lineHeight: "60px", letterSpacing: "-0.65px", fontWeight: "400" }],
        "display-lg": ["36px", { lineHeight: "40px", letterSpacing: "-0.9px", fontWeight: "400" }],
        "display-md": ["24px", { lineHeight: "32px", letterSpacing: "-0.6px", fontWeight: "700" }],
        "display-sm": ["20px", { lineHeight: "28px", fontWeight: "600" }],
        "eyebrow-mono": ["12px", { lineHeight: "16px", letterSpacing: "2.52px", fontWeight: "600" }],
        "eyebrow-up": ["14px", { lineHeight: "20px", letterSpacing: "1.8px", fontWeight: "600" }],
        "body-lg": ["18px", { lineHeight: "28px", fontWeight: "400" }],
        "body-md": ["16px", { lineHeight: "26px", fontWeight: "400" }],
        "body-sm": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        caption: ["12px", { lineHeight: "16px", fontWeight: "400" }],
        code: ["13px", { lineHeight: "18px", fontWeight: "400" }],
      },
      borderRadius: {
        none: "0",
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "8px",
        pill: "9999px",
      },
      letterSpacing: {
        eyebrow: "2.52px",
        tightish: "-0.6px",
      },
      keyframes: {
        "stream-line": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "stream-line": "stream-line 220ms ease-out",
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
        scan: "scan 4s linear infinite",
        "fade-in": "fade-in 200ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
