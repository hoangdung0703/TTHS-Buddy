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
      // One stacking scale for the whole app (root stacking context): 10 sticky docks and lifted
      // controls, 20 sticky banner, 30 menus and tooltips, 40 floating buttons, 50 drawers and
      // sheets, dialog = dialogs that can open from any of those (rendered in a body portal).
      zIndex: {
        dialog: "60"
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
        "fade-in-up": "fade-in-up 600ms cubic-bezier(.16,1,.3,1) both"
      }
    }
  },
  plugins: [tailwindcssAnimate]
};

export default config;
