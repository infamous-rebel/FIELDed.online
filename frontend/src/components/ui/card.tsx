import React from "react";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
  hover?: boolean;
}

const paddingClasses: Record<string, string> = {
  sm: "p-3",
  md: "p-4",
  lg: "p-5",
};

export function Card({
  children,
  className = "",
  padding = "md",
  hover = false,
}: CardProps) {
  return (
    <div
      className={`glass rounded-lg ${paddingClasses[padding]} ${
        hover ? "transition-colors hover:border-white/[0.10]" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}
