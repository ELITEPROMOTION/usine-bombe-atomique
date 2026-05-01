import { createContext, useContext, useId, useState } from "react";
import clsx from "clsx";

interface TabsCtx {
  value: string;
  setValue: (v: string) => void;
  baseId: string;
}

const Ctx = createContext<TabsCtx | null>(null);

interface TabsProps {
  value?: string;
  defaultValue?: string;
  onChange?: (v: string) => void;
  children: React.ReactNode;
  className?: string;
}

export function Tabs({
  value: controlled, defaultValue, onChange, children, className,
}: TabsProps) {
  const [internal, setInternal] = useState(defaultValue ?? "");
  const value = controlled ?? internal;
  const baseId = useId();
  const setValue = (v: string) => {
    setInternal(v);
    onChange?.(v);
  };
  return (
    <Ctx.Provider value={{ value, setValue, baseId }}>
      <div className={className}>{children}</div>
    </Ctx.Provider>
  );
}

export function TabList({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      role="tablist"
      className={clsx(
        "inline-flex items-center gap-1 p-1 rounded-lg",
        "bg-ink-800/40 border border-ink-700/40",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface TabProps {
  value: string;
  children: React.ReactNode;
  disabled?: boolean;
}

export function Tab({ value, children, disabled }: TabProps) {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("Tab must be inside <Tabs>");
  const active = ctx.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={`${ctx.baseId}-panel-${value}`}
      id={`${ctx.baseId}-tab-${value}`}
      disabled={disabled}
      onClick={() => ctx.setValue(value)}
      className={clsx(
        "px-3 py-1.5 rounded-md text-xs font-medium tracking-tight",
        "transition-all duration-150",
        active
          ? "bg-ink-900 text-ink-50 shadow-sm border border-ink-700/60"
          : "text-ink-300 hover:text-ink-100",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      {children}
    </button>
  );
}

interface PanelProps {
  value: string;
  children: React.ReactNode;
  className?: string;
}

export function TabPanel({ value, children, className }: PanelProps) {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("TabPanel must be inside <Tabs>");
  if (ctx.value !== value) return null;
  return (
    <div
      role="tabpanel"
      id={`${ctx.baseId}-panel-${value}`}
      aria-labelledby={`${ctx.baseId}-tab-${value}`}
      className={className}
    >
      {children}
    </div>
  );
}
