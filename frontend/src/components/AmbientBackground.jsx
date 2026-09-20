import { useEffect, useRef } from 'react';

/**
 * Slow drifting particle field behind the whole app.
 *
 * Kept deliberately cheap: particle count scales down on narrow viewports, the canvas
 * is capped at 1.5x device pixel ratio, and the animation stops entirely when the
 * document is hidden or the viewer prefers reduced motion.
 */
export default function AmbientBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const ctx = canvas.getContext('2d');
    let frame = null;
    let particles = [];
    let width = 0;
    let height = 0;

    const setup = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const count = width < 768 ? 16 : 40;
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.6 + Math.random() * 1.5,
        vx: (Math.random() - 0.5) * 0.11,
        vy: -0.045 - Math.random() * 0.09,
        alpha: 0.05 + Math.random() * 0.16,
      }));
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;

        if (p.y < -12) {
          p.y = height + 12;
          p.x = Math.random() * width;
        }
        if (p.x < -12) p.x = width + 12;
        if (p.x > width + 12) p.x = -12;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(150, 186, 168, ${p.alpha})`;
        ctx.fill();
      }
      frame = window.requestAnimationFrame(draw);
    };

    const start = () => {
      if (frame === null && !reduceMotion) frame = window.requestAnimationFrame(draw);
    };
    const stop = () => {
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
        frame = null;
      }
    };

    const onResize = () => {
      setup();
      if (reduceMotion) draw0();
    };
    const draw0 = () => {
      ctx.clearRect(0, 0, width, height);
      for (const p of particles) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(150, 186, 168, ${p.alpha})`;
        ctx.fill();
      }
    };

    const onVisibility = () => (document.hidden ? stop() : start());

    setup();
    if (reduceMotion) draw0();
    else start();

    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return (
    <>
      <div className="ambient-wash" aria-hidden="true" />
      <canvas ref={canvasRef} className="ambient-canvas" aria-hidden="true" />
      <div className="ambient-grain" aria-hidden="true" />
    </>
  );
}
