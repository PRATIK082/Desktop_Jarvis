export interface BadgeProps {
  variant?: "ok" | "warn" | "error" | "idle";
  className?: string;
  children: React.ReactNode;
}

export function Badge({
  variant = "idle",
  className = "",
  children,
}: BadgeProps) {
  const variants: Record<string, string> = {
    ok: "bg-status-ok/10 text-status-ok border border-status-ok/20",
    warn: "bg-status-warn/10 text-status-warn border border-status-warn/20",
    error: "bg-status-error/10 text-status-error border border-status-error/20",
    idle: "bg-status-idle/10 text-status-idle border border-status-idle/20",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
