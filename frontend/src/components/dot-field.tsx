"use client";

import { useEffect, useRef } from "react";

/**
 * Full-screen grid of dots that bends away from the pointer, brightens around it,
 * and sends a ripple out on click. A slow wave keeps it alive when the pointer is still.
 */
export function DotField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let w = 0, h = 0, dpr = 1, gap = 26;
    let homeX = new Float32Array(0), homeY = new Float32Array(0);
    let px = new Float32Array(0), py = new Float32Array(0);
    let vx = new Float32Array(0), vy = new Float32Array(0);
    const pointer = { x: -9999, y: -9999, tx: -9999, ty: -9999, active: false };
    const ripples: { x: number; y: number; t: number }[] = [];
    let raf = 0;
    let start = performance.now();

    function build() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas!.clientWidth; h = canvas!.clientHeight;
      canvas!.width = w * dpr; canvas!.height = h * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      gap = w < 640 ? 22 : 26;
      const cols = Math.ceil(w / gap) + 1, rows = Math.ceil(h / gap) + 1;
      const n = cols * rows;
      homeX = new Float32Array(n); homeY = new Float32Array(n);
      px = new Float32Array(n); py = new Float32Array(n);
      vx = new Float32Array(n); vy = new Float32Array(n);
      const ox = (w - (cols - 1) * gap) / 2, oy = (h - (rows - 1) * gap) / 2;
      let i = 0;
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++, i++) {
        homeX[i] = px[i] = ox + c * gap;
        homeY[i] = py[i] = oy + r * gap;
      }
    }

    function frame(now: number) {
      const t = (now - start) / 1000;
      // Pointer eases toward its target so the field feels weighted.
      pointer.x += (pointer.tx - pointer.x) * 0.18;
      pointer.y += (pointer.ty - pointer.y) * 0.18;
      const R = Math.min(260, Math.max(160, w * 0.16));
      const R2 = R * R;

      ctx!.clearRect(0, 0, w, h);

      // Soft light under the pointer.
      if (pointer.active) {
        const g = ctx!.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, R * 1.6);
        g.addColorStop(0, "rgba(255,255,255,0.07)");
        g.addColorStop(1, "rgba(255,255,255,0)");
        ctx!.fillStyle = g;
        ctx!.fillRect(0, 0, w, h);
      }

      for (let k = ripples.length - 1; k >= 0; k--) if (t - ripples[k].t > 2.2) ripples.splice(k, 1);

      const n = homeX.length;
      for (let i = 0; i < n; i++) {
        const hx = homeX[i], hy = homeY[i];
        // Ambient wave.
        let fx = Math.sin(hy * 0.012 + t * 0.7) * 3;
        let fy = Math.cos(hx * 0.01 + t * 0.6) * 3;
        let glow = 0;

        const dx = hx - pointer.x, dy = hy - pointer.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < R2) {
          const d = Math.sqrt(d2) || 1;
          const f = 1 - d / R;
          const push = f * f * 46;
          fx += (dx / d) * push; fy += (dy / d) * push;
          glow = f;
        }
        for (const rp of ripples) {
          const age = t - rp.t;
          const ring = age * 520;
          const rx = hx - rp.x, ry = hy - rp.y;
          const d = Math.sqrt(rx * rx + ry * ry) || 1;
          const band = 1 - Math.abs(d - ring) / 70;
          if (band > 0) {
            const s = band * (1 - age / 2.2) * 22;
            fx += (rx / d) * s; fy += (ry / d) * s;
            glow = Math.max(glow, band * (1 - age / 2.2));
          }
        }

        // Spring toward home + force.
        vx[i] = (vx[i] + (hx + fx - px[i]) * 0.12) * 0.78;
        vy[i] = (vy[i] + (hy + fy - py[i]) * 0.12) * 0.78;
        px[i] += vx[i]; py[i] += vy[i];

        const a = 0.2 + glow * 0.75;
        const s = 1.3 + glow * 1.9;
        ctx!.fillStyle = `rgba(237,237,239,${a})`;
        ctx!.fillRect(px[i] - s / 2, py[i] - s / 2, s, s);
      }

      // Fade the edges into the background.
      const v = ctx!.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.25, w / 2, h / 2, Math.max(w, h) * 0.75);
      v.addColorStop(0, "rgba(11,11,13,0)");
      v.addColorStop(1, "rgba(11,11,13,0.8)");
      ctx!.fillStyle = v;
      ctx!.fillRect(0, 0, w, h);

      if (!reduce) raf = requestAnimationFrame(frame);
    }

    function move(e: PointerEvent) {
      const rect = canvas!.getBoundingClientRect();
      pointer.tx = e.clientX - rect.left; pointer.ty = e.clientY - rect.top;
      if (!pointer.active) { pointer.x = pointer.tx; pointer.y = pointer.ty; pointer.active = true; }
      if (reduce) requestAnimationFrame(frame);
    }
    function leave() { pointer.active = false; pointer.tx = pointer.ty = -9999; }
    function down(e: PointerEvent) {
      const rect = canvas!.getBoundingClientRect();
      ripples.push({ x: e.clientX - rect.left, y: e.clientY - rect.top, t: (performance.now() - start) / 1000 });
      move(e);
    }
    function resize() { build(); if (reduce) requestAnimationFrame(frame); }

    build();
    start = performance.now();
    raf = requestAnimationFrame(frame);
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerdown", down, { passive: true });
    document.addEventListener("pointerleave", leave);
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerdown", down);
      document.removeEventListener("pointerleave", leave);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={className} />;
}
