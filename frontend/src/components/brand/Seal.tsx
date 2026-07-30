"use client";

import { type CSSProperties, useId } from "react";

import { cn } from "@/lib/utils";

interface SealProps {
  size?: number;
  className?: string;
  animate?: boolean;
  /** Delay before the stamp-down animation fires, in ms — lets a page sequence the seal as the last beat. */
  delayMs?: number;
}

/**
 * Vector stamp motif — a simplified line-art seal, not a scan of a real government dấu.
 * Ring text and center numeral are invented copy tied to the product's own Điều 13 framing,
 * never a real agency name, to avoid reading as an official state mark.
 */
export function Seal({ size = 128, className, animate = true, delayMs = 250 }: SealProps) {
  const arcId = useId();

  return (
    <span className="relative inline-block" style={{ width: size, height: size }}>
      {/* Decorative glow, drawn behind the seal and NOT clipped, so it can fade out past the
          ink instead of being cut off by the circular hit-region below. */}
      <span
        aria-hidden="true"
        className="absolute inset-0 rounded-full shadow-[0_10px_18px_rgba(17,27,41,0.22)]"
      />

      {/*
        `:hover` for an ancestor is decided by that ancestor's OWN box, regardless of any
        clip-path on a descendant — so the circular hit-region has to live on the element
        `group-hover` actually watches, not on a child. `clip-path: circle(50%)` here also
        restricts pointer-events/hit-testing to the circle itself, not the square the circle
        is inscribed in. Without it, the four transparent corners of that square (visually
        just page background) still counted as "hovering the seal": sweeping the mouse across
        them repeatedly re-triggered the wiggle, which read as flicker. Binding the hover
        trigger to this fixed, non-transformed wrapper (rather than the svg, which itself
        rotates/scales) also avoids a second feedback loop — box moves out from under the
        cursor → hover ends → box snaps back → hover starts again.
      */}
      <span className="group absolute inset-0" style={{ clipPath: "circle(50%)" }}>
        <svg
          viewBox="0 0 200 200"
          width={size}
          height={size}
          className={cn(
            "select-none text-seal-red-600 transition-transform duration-300 ease-spring group-hover:animate-seal-wiggle",
            animate && "animate-stamp-down",
            !animate && "rotate-[-8deg]",
            className
          )}
          style={{
            transformOrigin: "50% 50%",
            // Scoped as a custom property (not `animationDelay`) so it only feeds the stamp-down
            // keyframe's own delay slot and can't leak into the hover wiggle's inline cascade.
            ...(animate ? ({ "--seal-delay": `${delayMs}ms` } as CSSProperties) : {})
          }}
          aria-hidden="true"
        >
          <defs>
            <path id={arcId} d="M 34 122 A 84 84 0 1 1 166 122" fill="none" />
          </defs>

          <circle cx="100" cy="100" r="90" fill="none" stroke="currentColor" strokeWidth="2.5" />
          <circle cx="100" cy="100" r="78" fill="none" stroke="currentColor" strokeWidth="1" />

          <text fill="currentColor" fontSize="12.5" fontWeight={600} letterSpacing="3.2">
            <textPath href={`#${arcId}`} startOffset="50%" textAnchor="middle">
              • TINH THẦN ĐIỀU 13 •
            </textPath>
          </text>

          <g stroke="currentColor" strokeWidth="1.5">
            <path d="M 44 133 L 49 141 L 40 139 Z" fill="currentColor" />
            <path d="M 156 133 L 151 141 L 160 139 Z" fill="currentColor" />
          </g>

          <text
            x="100"
            y="95"
            textAnchor="middle"
            fontFamily="var(--font-serif)"
            fontSize="46"
            fontWeight={600}
            fill="currentColor"
          >
            13
          </text>
          <text
            x="100"
            y="122"
            textAnchor="middle"
            fontSize="10.5"
            fontWeight={600}
            letterSpacing="2"
            fill="currentColor"
          >
            BLTTHS · 2015
          </text>
        </svg>
      </span>
    </span>
  );
}
