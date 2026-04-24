import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Sparkles, Workflow, FolderOpen, LogOut, Crown, Inbox,
  Menu, X, Brain, ShieldCheck, Activity, Building2, Zap, Layers,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/stores/authStore";
import clsx from "clsx";

const nav = [
  { to: "/",             label: "Vue d'ensemble",   Icon: LayoutDashboard },
  { to: "/ceo",          label: "CEO",              Icon: Crown },
  { to: "/ahmed_inbox",  label: "Boite A/B/C",      Icon: Inbox },
  { to: "/domains",      label: "Domaines (5)",     Icon: Layers },
  { to: "/fleet",        label: "Fleet",            Icon: Building2 },
  { to: "/automation",   label: "Automation",       Icon: Zap },
  { to: "/cognition",    label: "Cognition",        Icon: Brain },
  { to: "/truth",        label: "Truth Engine",     Icon: ShieldCheck },
  { to: "/observability",label: "Observabilite",    Icon: Activity },
  { to: "/new",          label: "Nouveau projet",   Icon: Sparkles },
  { to: "/projects",     label: "Historique",       Icon: FolderOpen },
];

export function AppShell() {
  const { email, logout } = useAuth();
  const nav2 = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="min-h-screen flex bg-ink-950 bg-grid-dots">
      {/* Drawer mobile (< lg) */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden
        />
      )}
      <aside
        className={clsx(
          "fixed lg:static z-50 flex flex-col w-64 shrink-0",
          "border-r border-ink-800 bg-ink-900/80 lg:bg-ink-900/40 backdrop-blur",
          "h-screen transition-transform duration-200",
          drawerOpen ? "translate-x-0" : "-translate-x-full",
          "lg:translate-x-0",
        )}
      >
        <div className="h-16 px-5 flex items-center border-b border-ink-800 justify-between">
          <Logo />
          <button
            onClick={() => setDrawerOpen(false)}
            className="lg:hidden text-ink-300 hover:text-ink-100"
            aria-label="Fermer le menu"
          >
            <X size={18} />
          </button>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {nav.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setDrawerOpen(false)}
              className={({ isActive }) => clsx(
                "group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all",
                isActive
                  ? "bg-ink-800/80 text-ink-50 shadow-inner"
                  : "text-ink-300 hover:text-ink-50 hover:bg-ink-800/50",
              )}
            >
              {({ isActive }) => (
                <>
                  <span className={clsx(
                    "w-1 h-5 rounded-full transition-all",
                    isActive ? "bg-gradient-to-b from-gold-300 to-gold-500" : "bg-transparent",
                  )} />
                  <Icon size={16} className={clsx(isActive ? "text-gold-300" : "text-ink-400 group-hover:text-ink-100")} />
                  <span className="font-medium tracking-tight">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-ink-800">
          <div className="px-3 py-2.5 flex items-center gap-3 rounded-lg bg-ink-800/40">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold-300 to-gold-600 flex items-center justify-center text-ink-950 text-xs font-semibold">
              {email?.[0]?.toUpperCase() ?? "?"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-ink-200 truncate">{email ?? "—"}</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">
                Ahmed CEO
              </div>
            </div>
            <button
              onClick={() => { logout(); nav2("/login"); }}
              className="text-ink-400 hover:text-danger transition-colors p-1.5 rounded-md hover:bg-ink-800"
              title="Deconnexion"
              aria-label="Deconnexion"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 shrink-0 border-b border-ink-800 bg-ink-900/40 backdrop-blur flex items-center px-4 lg:px-8 gap-3">
          <button
            onClick={() => setDrawerOpen(true)}
            className="lg:hidden text-ink-200 hover:text-ink-50 p-2"
            aria-label="Ouvrir le menu"
          >
            <Menu size={20} />
          </button>
          <div className="lg:hidden"><Logo /></div>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full bg-ink-800/60 border border-ink-700/60 text-ink-200">
              <Workflow size={11} className="text-gold-300" />
              UBA v0.2 · 26 tasks · Truth V5.3 · Cognition V5.4 · Automation V5.5
            </span>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
