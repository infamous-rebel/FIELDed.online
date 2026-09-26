import React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function Input({
  label,
  error,
  helperText,
  id,
  className = "",
  ...props
}: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="space-y-1">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-xs font-medium text-[var(--text-secondary)]"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full rounded-lg border bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs
          text-[var(--text-primary)] placeholder-[var(--text-muted)]
          border-[var(--border-default)]
          focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? "border-[var(--danger)] focus:border-[var(--danger)] focus:ring-[var(--danger)]" : ""}
          ${className}`}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={
          error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined
        }
        {...props}
      />
      {error && (
        <p
          id={`${inputId}-error`}
          className="text-xs text-[var(--danger)]"
          role="alert"
        >
          {error}
        </p>
      )}
      {helperText && !error && (
        <p
          id={`${inputId}-helper`}
          className="text-xs text-[var(--text-muted)]"
        >
          {helperText}
        </p>
      )}
    </div>
  );
}
