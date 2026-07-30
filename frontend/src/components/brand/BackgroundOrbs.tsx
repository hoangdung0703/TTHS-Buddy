// Soft blurred gradient orbs behind the Welcome/Sign in/Sign up pages — the editorial
// palette's background treatment (design/figma-export reference), shared so the three
// pages read as one consistent surface rather than three separate one-off backgrounds.
export function BackgroundOrbs() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true">
      <div
        className="absolute rounded-full"
        style={{
          width: 680,
          height: 680,
          top: -200,
          right: -180,
          background: "radial-gradient(circle, rgba(30,36,96,0.13) 0%, transparent 70%)",
          filter: "blur(72px)"
        }}
      />
      <div
        className="absolute rounded-full"
        style={{
          width: 520,
          height: 520,
          bottom: 80,
          left: -140,
          background: "radial-gradient(circle, rgba(184,154,82,0.11) 0%, transparent 70%)",
          filter: "blur(64px)"
        }}
      />
      <div
        className="absolute rounded-full"
        style={{
          width: 360,
          height: 360,
          top: "45%",
          right: "30%",
          background: "radial-gradient(circle, rgba(30,36,96,0.07) 0%, transparent 70%)",
          filter: "blur(56px)"
        }}
      />
    </div>
  );
}
