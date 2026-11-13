/** Loading placeholder block. */
export function Skeleton({ className = "h-4" }: { className?: string }) {
  return <div aria-hidden className={`motion-fade animate-pulse rounded bg-raised ${className}`} />;
}

/** Panel-shaped loading skeleton. */
export function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <section className="rounded-panel border border-hairline bg-panel p-4 sm:p-5">
      <Skeleton className="mb-4 h-3 w-28" />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-full max-w-[85%]" />
        ))}
      </div>
    </section>
  );
}
