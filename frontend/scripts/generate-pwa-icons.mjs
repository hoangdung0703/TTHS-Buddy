// Renders PWA icons from the Sidebar's logo mark (lucide "Scale" icon in a navy
// bg-primary square, see src/components/layout/Sidebar.tsx) instead of a new design.
// Re-run with `node scripts/generate-pwa-icons.mjs` if the logo or palette ever changes.
import sharp from "sharp";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const NAVY = "#1E2460";
const IVORY = "#F5F0E8";

// Path data copied from lucide-react's Scale icon (node_modules/lucide-react/dist/esm/icons/scale.js).
const SCALE_PATHS = [
  "m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
  "m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
  "M7 21h10",
  "M12 3v18",
  "M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"
];

function scaleIconSvg({ box, iconScale, cornerRadius, background }) {
  const iconSize = box * iconScale;
  const offset = (box - iconSize) / 2;
  // lucide's native viewBox is 0 0 24 24 with strokeWidth 2 at that scale.
  const strokeWidth = 2 * (iconSize / 24);

  const backgroundRect = background
    ? `<rect width="${box}" height="${box}" rx="${cornerRadius}" fill="${NAVY}" />`
    : "";

  return `
<svg width="${box}" height="${box}" viewBox="0 0 ${box} ${box}" xmlns="http://www.w3.org/2000/svg">
  ${backgroundRect}
  <g transform="translate(${offset} ${offset}) scale(${iconSize / 24})"
     fill="none" stroke="${IVORY}" stroke-width="${2}" stroke-linecap="round" stroke-linejoin="round">
    ${SCALE_PATHS.map((d) => `<path d="${d}" />`).join("\n    ")}
  </g>
</svg>`.trim();
}

const outDir = path.resolve(import.meta.dirname, "../public/icons");

const targets = [
  // Standard "any" purpose icons - full-bleed rounded-square background, matches the Sidebar mark.
  { file: "icon-192.png", box: 192, iconScale: 0.62, cornerRadius: 192 * 0.22, background: true },
  { file: "icon-512.png", box: 512, iconScale: 0.62, cornerRadius: 512 * 0.22, background: true },
  // iOS applies its own rounding/mask, so no corner radius here.
  { file: "apple-touch-icon.png", box: 180, iconScale: 0.62, cornerRadius: 0, background: true },
  // "maskable" purpose needs the icon kept inside Android's ~80% safe zone.
  { file: "maskable-icon-512.png", box: 512, iconScale: 0.5, cornerRadius: 0, background: true }
];

await mkdir(outDir, { recursive: true });

for (const target of targets) {
  const svg = scaleIconSvg(target);
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  await writeFile(path.join(outDir, target.file), png);
  console.log(`wrote ${target.file}`);
}
