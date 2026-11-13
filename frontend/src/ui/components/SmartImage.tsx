import { useState } from "react";

/**
 * Self-hosted image with graceful procedural fallback: if the file fails
 * to load (offline habitat, missing asset) the slot keeps its gradient
 * placeholder instead of showing a broken image. `disabled` renders only
 * the placeholder (Reduce effects mode).
 *
 * Note: eager by default. These images are above-the-fold anchors on their
 * own pages (never shipped with the Hub's first paint), so eager loading
 * is both safe and more reliable across browsers than native lazy loading.
 */
export function SmartImage({
  src,
  alt,
  className = "",
  disabled = false,
}: {
  src: string;
  alt: string;
  className?: string;
  disabled?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (disabled || failed) {
    return (
      <div
        role={alt ? "img" : undefined}
        aria-label={alt || undefined}
        className={`bg-[radial-gradient(120%_120%_at_30%_20%,#16324f_0%,#0b1220_55%,#05070d_100%)] ${className}`}
        aria-hidden={alt === "" ? true : undefined}
      />
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="eager"
      decoding="async"
      onError={() => setFailed(true)}
      className={className}
    />
  );
}
