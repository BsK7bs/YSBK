import React, { useEffect, useRef } from "react";

/**
 * Full-viewport premium background:
 *  - animated gradient mesh (aurora blobs)
 *  - animated grid with radial fade
 *  - light beams sweeping across
 *  - floating glowing particles (canvas)
 *  - noise texture
 *  - mouse spotlight (CSS variables driven)
 */
export default function AnimatedBackground() {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);

  // Mouse spotlight follow
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - r.left}px`);
      el.style.setProperty("--my", `${e.clientY - r.top}px`);
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  // Particle system
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let raf = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let particles = [];

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = canvas.offsetWidth * dpr;
      canvas.height = canvas.offsetHeight * dpr;
      const count = Math.min(70, Math.floor((canvas.offsetWidth * canvas.offsetHeight) / 24000));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: (Math.random() * 1.6 + 0.4) * dpr,
        vx: (Math.random() - 0.5) * 0.18 * dpr,
        vy: (Math.random() - 0.5) * 0.18 * dpr,
        hue: 190 + Math.random() * 60,
        a: Math.random() * 0.5 + 0.25,
      }));
    };
    resize();
    window.addEventListener("resize", resize);

    const step = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
        const grd = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 6);
        grd.addColorStop(0, `hsla(${p.hue}, 90%, 65%, ${p.a})`);
        grd.addColorStop(1, "hsla(220, 40%, 50%, 0)");
        ctx.fillStyle = grd;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 6, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(step);
    };
    step();
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      aria-hidden="true"
      style={{
        // fallback initial spotlight position
        "--mx": "50%",
        "--my": "40%",
      }}
    >
      {/* Base gradient wash */}
      <div className="absolute inset-0 bg-gradient-to-b from-background via-background to-background" />

      {/* Aurora blobs */}
      <div className="absolute -top-40 -left-32 h-[520px] w-[520px] rounded-full blur-3xl opacity-70 animate-aurora"
        style={{ background: "radial-gradient(circle at 30% 30%, hsl(var(--primary) / 0.55), transparent 60%)" }} />
      <div className="absolute top-1/3 -right-40 h-[560px] w-[560px] rounded-full blur-3xl opacity-70 animate-aurora"
        style={{ background: "radial-gradient(circle at 60% 40%, hsl(var(--info) / 0.5), transparent 60%)", animationDelay: "-8s" }} />
      <div className="absolute bottom-0 left-1/3 h-[460px] w-[460px] rounded-full blur-3xl opacity-60 animate-aurora"
        style={{ background: "radial-gradient(circle at 40% 60%, hsl(var(--chart-3) / 0.4), transparent 60%)", animationDelay: "-14s" }} />

      {/* Animated grid with radial fade */}
      <div className="absolute inset-0 grid-bg animate-grid mask-radial-fade opacity-70" />

      {/* Light beams */}
      <div className="absolute inset-y-0 left-0 w-full overflow-hidden">
        <div className="absolute top-10 left-0 h-72 w-56 rotate-12 blur-2xl animate-beam"
          style={{ background: "linear-gradient(90deg, transparent, hsl(var(--primary) / 0.35), transparent)" }} />
        <div className="absolute top-1/2 left-0 h-56 w-52 rotate-6 blur-2xl animate-beam"
          style={{ background: "linear-gradient(90deg, transparent, hsl(var(--info) / 0.3), transparent)", animationDelay: "-3s" }} />
      </div>

      {/* Particles */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />

      {/* Mouse spotlight */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(600px circle at var(--mx) var(--my), hsl(var(--primary) / 0.10), transparent 60%)",
        }}
      />

      {/* Noise */}
      <div
        className="absolute inset-0 opacity-[0.06] mix-blend-overlay"
        style={{
          backgroundImage:
            "radial-gradient(hsl(var(--foreground)) 1px, transparent 1px)",
          backgroundSize: "3px 3px",
        }}
      />
    </div>
  );
}
