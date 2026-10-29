import { type HTMLAttributes, type PropsWithChildren } from "react";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: "none" | "sm" | "md" | "lg";
}

export function Card({
  className = "",
  padding = "md",
  children,
}: PropsWithChildren<CardProps>) {
  const paddingClasses: Record<string, string> = {
    none: "p-0",
    sm: "p-3",
    md: "p-4",
    lg: "p-6",
  };
  return (
    <div
      className={`bg-surface-graphite border border-surface-panel rounded-xl ${paddingClasses[padding]} ${className}`}
      {...(className ? {} : {})}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
}

export function CardHeader({
  className = "",
  title,
  subtitle,
}: CardHeaderProps) {
  return (
    <div className={`mb-3 ${className}`}>
      {title && <h3 className="text-sm font-semibold text-light">{title}</h3>}
      {subtitle && <p className="text-xs text-surface-panel">{subtitle}</p>}
    </div>
  );
}
