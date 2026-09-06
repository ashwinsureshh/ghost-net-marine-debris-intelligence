import { ChevronsLeft, ListChecks, Moon, PanelLeft, SlidersHorizontal, Sun, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The application rail: identity, navigation, and the theme control.
 *
 * **Every item here is an existing panel.** "Detections", "Rejected" and
 * "Controls" are the three tabs this replaces, and "Diagnostics" opens the run
 * diagnostics drawer that was already there. Nothing on this rail is new
 * functionality wearing a new label — an operator console that advertises a
 * capability it does not have is worse than one that looks plainer.
 *
 * Collapsed it is an icon rail, so the map gains ~180px on a small screen
 * without losing navigation. The state lives in App because the grid template
 * has to change with it.
 */

export type PanelId = "dispatch" | "rejected" | "controls";

interface SidebarProps {
  tab: PanelId;
  onTabChange: (tab: PanelId) => void;
  dispatchCount?: number;
  rejectedCount?: number;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
  diagnosticsOpen: boolean;
  onToggleDiagnostics: () => void;
}

function NavItem({
  icon: Icon,
  label,
  count,
  active,
  collapsed,
  onClick,
  ...rest
}: {
  icon: typeof ListChecks;
  label: string;
  count?: number;
  active?: boolean;
  collapsed: boolean;
  onClick: () => void;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2.5 px-3 py-[7px] text-left text-[13px]",
        "transition-colors duration-150",
        collapsed && "justify-center px-0",
        // A tonal fill and a left rule, not a floating rounded chip.
        active
          ? "row-rule bg-accent/60 font-medium text-foreground"
          : "text-muted-foreground hover:bg-accent/30 hover:text-foreground",
      )}
      {...rest}
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && (
        <>
          <span className="min-w-0 flex-1 truncate">{label}</span>
          {count !== undefined && count > 0 && (
            <span className="tabular shrink-0 font-mono text-[11px] text-muted-foreground">
              {count}
            </span>
          )}
        </>
      )}
    </button>
  );
}

export function Sidebar({
  tab,
  onTabChange,
  dispatchCount,
  rejectedCount,
  collapsed,
  diagnosticsOpen,
  onToggleDiagnostics,
}: SidebarProps) {
  return (
    <div className="flex shrink-0 flex-col bg-card">
      {/* -- identity ------------------------------------------------------ */}
      <div
        className={cn(
          "flex shrink-0 items-center gap-2.5 px-3 py-3",
          collapsed && "justify-center px-0",
        )}
      >
        <div
          aria-hidden="true"
          className="flex size-7 shrink-0 items-center justify-center rounded-sm bg-primary/12 text-primary"
        >
          {/* Net-and-wave mark: drawn, not an emoji. */}
          <svg viewBox="0 0 24 24" className="size-4" fill="none" strokeWidth="1.6">
            <path
              d="M2 17c2.2 0 2.2 2 4.4 2s2.2-2 4.4-2 2.2 2 4.4 2 2.2-2 4.4-2"
              stroke="currentColor"
              strokeLinecap="round"
            />
            <path
              d="M4 4l6 6m4 4l6 6M10 4l-6 6m16 4l-6 6"
              stroke="currentColor"
              strokeLinecap="round"
              opacity=".6"
            />
          </svg>
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold leading-tight tracking-tight">
              GhostNet
            </p>
            <p className="truncate text-[11px] leading-tight text-muted-foreground">
              Marine Debris Intelligence
            </p>
          </div>
        )}
      </div>

      {/* -- navigation ---------------------------------------------------- */}
      <nav aria-label="Panels" className="flex flex-col pb-2">
        {!collapsed && (
          <p className="px-3 pb-1.5 pt-3 text-[11px] font-medium text-foreground">
            Investigation
          </p>
        )}
        <NavItem
          icon={ListChecks}
          label="Detections"
          count={dispatchCount}
          active={tab === "dispatch"}
          collapsed={collapsed}
          onClick={() => onTabChange("dispatch")}
          aria-current={tab === "dispatch" ? "page" : undefined}
        />
        <NavItem
          icon={XCircle}
          label="Rejected"
          count={rejectedCount}
          active={tab === "rejected"}
          collapsed={collapsed}
          onClick={() => onTabChange("rejected")}
          aria-current={tab === "rejected" ? "page" : undefined}
        />

        {!collapsed && (
          <p className="px-3 pb-1.5 pt-4 text-[11px] font-medium text-foreground">
            Run
          </p>
        )}
        <NavItem
          icon={SlidersHorizontal}
          label="Controls"
          active={tab === "controls"}
          collapsed={collapsed}
          onClick={() => onTabChange("controls")}
          aria-current={tab === "controls" ? "page" : undefined}
        />
        <NavItem
          icon={PanelLeft}
          label="Diagnostics"
          active={diagnosticsOpen}
          collapsed={collapsed}
          onClick={onToggleDiagnostics}
          aria-expanded={diagnosticsOpen}
        />
      </nav>
    </div>
  );
}

/** The rail's footer controls, pinned to the bottom of the sidebar column. */
export function SidebarFooter({
  collapsed,
  onToggleCollapsed,
  isDark,
  onToggleTheme,
}: Pick<SidebarProps, "collapsed" | "onToggleCollapsed" | "isDark" | "onToggleTheme">) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-1 border-t border-border bg-card px-2 py-1.5",
        collapsed && "flex-col",
      )}
    >
      <button
        type="button"
        onClick={onToggleTheme}
        title={isDark ? "Switch to light theme" : "Switch to dark theme"}
        aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
        className="flex cursor-pointer items-center justify-center rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
      >
        {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </button>
      <button
        type="button"
        onClick={onToggleCollapsed}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        className="flex cursor-pointer items-center justify-center rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
      >
        <ChevronsLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} />
      </button>
    </div>
  );
}
