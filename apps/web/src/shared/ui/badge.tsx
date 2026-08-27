import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/shared/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

const GRADE_STYLES: Record<string, string> = {
  GREEN: "border-transparent bg-grade-green text-white",
  YELLOW: "border-transparent bg-grade-yellow text-white",
  ORANGE: "border-transparent bg-grade-orange text-white",
  RED: "border-transparent bg-grade-red text-white",
  BLACK: "border-transparent bg-grade-black text-white",
};

export function GradeBadge({
  grade,
  className,
  size = "md",
}: {
  grade: string;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-md font-bold tracking-wide",
        size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs",
        GRADE_STYLES[grade] ?? "border border-border bg-muted text-muted-foreground",
        className,
      )}
    >
      {grade}
    </span>
  );
}

export { badgeVariants };
