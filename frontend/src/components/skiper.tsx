"use client";

/**
 * Small interaction pieces adapted from Skiper UI (https://skiper-ui.com):
 * - TextRoll: skiper58 "Text roll navigation"
 * - ProgressiveBlur: skiper41 "Progressive Blur"
 * - AnimatedNumber: skiper37 "Animated number" (Number Flow)
 * Free Skiper UI components, used under its license (attribution required).
 */

import NumberFlow from "@number-flow/react";
import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const STAGGER = 0.025;

/** Letters roll up on hover. Hover is driven by a parent with variants "initial" / "hovered". */
export function TextRoll({ children, className }: { children: string; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <span className={className}>{children}</span>;
  const letters = children.split("");
  const row = (from: string | number, to: string | number) =>
    letters.map((l, i) => (
      <motion.span key={i} className="inline-block whitespace-pre"
        variants={{ initial: { y: from }, hovered: { y: to } }}
        transition={{ ease: [0.65, 0, 0.35, 1], duration: 0.35, delay: STAGGER * i }}>
        {l}
      </motion.span>
    ));
  return (
    <span className={cn("relative block overflow-hidden", className)} aria-label={children}>
      <span aria-hidden className="block">{row(0, "-100%")}</span>
      <span aria-hidden className="absolute inset-0 block">{row("100%", 0)}</span>
    </span>
  );
}

/** Edge fade with backdrop blur, for the bottom of scroll areas. */
export function ProgressiveBlur({ position = "bottom", height = "96px", color = "#0B0B0D", blur = "4px", className }: {
  position?: "top" | "bottom"; height?: string; color?: string; blur?: string; className?: string;
}) {
  const top = position === "top";
  return (
    <div aria-hidden className={cn("pointer-events-none absolute inset-x-0 z-10 select-none", className)}
      style={{
        [top ? "top" : "bottom"]: 0,
        height,
        background: `linear-gradient(to ${top ? "top" : "bottom"}, transparent, ${color})`,
        maskImage: `linear-gradient(to ${top ? "bottom" : "top"}, #000 50%, transparent)`,
        WebkitMaskImage: `linear-gradient(to ${top ? "bottom" : "top"}, #000 50%, transparent)`,
        backdropFilter: `blur(${blur})`,
        WebkitBackdropFilter: `blur(${blur})`,
      }} />
  );
}

/** Number that rolls up from 0 on mount and rolls its digits when the value changes. */
export function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(value));
    return () => cancelAnimationFrame(id);
  }, [value]);
  return <NumberFlow value={shown} className={className} willChange />;
}
