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
        }
      },
      animation: {
        "fade-in-up": "fade-in-up 600ms ease-out"
      }
    }
  },
  plugins: [tailwindcssAnimate]
};

export default config;
