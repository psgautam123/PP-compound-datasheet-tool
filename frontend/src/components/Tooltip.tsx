import { useState, type ReactNode } from "react";

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="tooltip-wrap"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
    >
      {children}
      {open && (
        <span className="tooltip-bubble" role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
}
