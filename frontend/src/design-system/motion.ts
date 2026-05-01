/**
 * Motion presets pour framer-motion (Phase 9O).
 *
 * Centralise les courbes et delays utilises dans le design system.
 * Permet une coherence visuelle cross-component.
 */
import type { Transition, Variants } from "framer-motion";

export const easing = {
  smooth: [0.2, 0.8, 0.2, 1] as const,
  inOut: [0.4, 0, 0.2, 1] as const,
  out: [0, 0, 0.2, 1] as const,
  spring: { type: "spring", stiffness: 320, damping: 28 } as Transition,
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.4, ease: easing.smooth } },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show:   { opacity: 1, transition: { duration: 0.25, ease: easing.out } },
};

export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 16 },
  show:   { opacity: 1, x: 0, transition: easing.spring },
  exit:   { opacity: 0, x: 16, transition: { duration: 0.18, ease: easing.inOut } },
};

export const stagger = (delay = 0.05): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: delay } },
});

export const presets = {
  fadeUp, fadeIn, slideInRight, stagger,
} as const;
