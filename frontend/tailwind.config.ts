import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}"
  ],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: {
        "2xl": "1400px"
      }
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Segoe UI", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"]
      },
      colors: {
        // Full steel-blue ramp (base 500 = #4682B4) for spots that need a specific shade
        // rather than the semantic primary/accent tokens below. Change the brand hue here only.
        "steel-blue": {
          50: "#EFF6FB",
          100: "#DBE9F5",
          200: "#BED6E9",
          300: "#96BBD9",
          400: "#6B9EC7",
          500: "#4682B4",
          600: "#356B97",
          700: "#27557C",
          800: "#1C405F",
          900: "#112B41"
        },
        // Seal accent — deliberate second hue, reserved for the stamp motif only. Do not spread into buttons/backgrounds.
        "seal-red": {
          50: "#FBEEEC",
          400: "#B85347",
          600: "#9C2B1F",
          700: "#7C2118"
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))"
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))"
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))"
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))"
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))"
        }
      },
      borderRadius: {
        xl: "1rem",
        lg: "0.75rem",
        md: "0.5rem"
      },
      // Two-curve motion system, reused everywhere instead of one-off easings per element:
      // "confident" (expo-out) for every entrance/settle; "spring" (back-out) for anything
      // that should feel physical — the stamp itself, and hover feedback that echoes it.
      transitionTimingFunction: {
        confident: "cubic-bezier(.16,1,.3,1)",
        spring: "cubic-bezier(.34,1.56,.64,1)"
      },
      keyframes: {
        "fade-in-up": {
          from: {
            opacity: "0",
            transform: "translateY(12px)"
          },
          to: {
            opacity: "1",
            transform: "translateY(0)"
          }
        },
        "stamp-down": {
          "0%": {
            opacity: "0",
            transform: "translateY(-58px) rotate(-28deg) scale(1.6)"
          },
          "50%": {
            opacity: "1",
            transform: "translateY(4px) rotate(-5deg) scale(0.93)"
          },
          "70%": {
            transform: "translateY(-3px) rotate(-10deg) scale(1.03)"
          },
          "85%": {
            transform: "translateY(1px) rotate(-7deg) scale(0.99)"
          },
          "100%": {
            opacity: "1",
            transform: "translateY(0) rotate(-8deg) scale(1)"
          }
        },
        "seal-wiggle": {
          "0%, 100%": { transform: "rotate(-8deg)" },
          "30%": { transform: "rotate(-12deg)" },
          "60%": { transform: "rotate(-4deg)" }
        },
        "rise-in": {
          from: {
            opacity: "0",
            transform: "translateY(28px)"
          },
          to: {
            opacity: "1",
            transform: "translateY(0)"
          }
        }
      },
      animation: {
        "fade-in-up": "fade-in-up 600ms cubic-bezier(.16,1,.3,1) both",
        "stamp-down": "stamp-down 900ms cubic-bezier(.34,1.56,.64,1) var(--seal-delay, 250ms) both",
        "seal-wiggle": "seal-wiggle 480ms cubic-bezier(.34,1.56,.64,1) forwards",
        "rise-in": "rise-in 700ms cubic-bezier(.16,1,.3,1) both"
      }
    }
  },
  plugins: [tailwindcssAnimate]
};

export default config;
