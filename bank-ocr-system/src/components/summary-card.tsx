"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface SummaryCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: { value: string; positive: boolean };
  className?: string;
  accentColor?: string;
}

export function SummaryCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  className,
  accentColor = "bg-primary/10 text-primary",
}: SummaryCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className={cn(
        "relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-sm transition-shadow hover:shadow-md",
        className
      )}
    >
      {/* Top row */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
          <p className="text-xl font-bold tracking-tight text-foreground">
            {value}
          </p>
          {subtitle && (
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
        <div
          className={cn(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
            accentColor
          )}
        >
          {icon}
        </div>
      </div>

      {/* Trend */}
      {trend && (
        <div className="mt-3 flex items-center gap-1.5">
          <span
            className={cn(
              "inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-semibold",
              trend.positive
                ? "bg-[var(--credit)]/10 text-[var(--credit)]"
                : "bg-[var(--debit)]/10 text-[var(--debit)]"
            )}
          >
            {trend.positive ? "↑" : "↓"} {trend.value}
          </span>
          <span className="text-xs text-muted-foreground">vs last period</span>
        </div>
      )}

      {/* Decorative gradient */}
      <div className="pointer-events-none absolute -bottom-4 -right-4 h-24 w-24 rounded-full bg-primary/5 blur-2xl" />
    </motion.div>
  );
}
