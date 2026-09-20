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
    <div className="space-y-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-[var(--text-primary)]"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full rounded-lg border bg-[var(--bg-surface)] px-3 py-2 text-sm
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
          className="text-sm text-[var(--danger)]"
          role="alert"
        >
          {error}
        </p>
      )}
      {helperText && !error && (
        <p
          id={`${inputId}-helper`}
          className="text-sm text-[var(--text-muted)]"
        >
          {helperText}
        </p>
      )}
    </div>
  );
}
