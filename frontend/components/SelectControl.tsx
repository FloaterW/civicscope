import type { ReactNode } from "react";

/** The same 44px control and focus treatment in the toolbar and detail panel. */
export function SelectControl({ id, label, value, onChange, disabled, icon, children }: {
  id?: string;
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  disabled?: boolean;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-11 min-w-0 items-center gap-2 rounded-md border border-civic-line bg-civic-panel p-1 shadow-panel transition focus-within:border-civic-teal">
      {icon}
      <select id={id} value={value} onChange={event => onChange(event.target.value)} disabled={disabled} aria-label={label}
        className="h-full min-w-0 flex-1 rounded border-0 bg-civic-panel px-1 text-sm font-medium text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-panel disabled:cursor-not-allowed disabled:text-civic-muted disabled:opacity-50">
        {children}
      </select>
    </div>
  );
}
