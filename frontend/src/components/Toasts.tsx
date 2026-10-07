import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import * as React from "react";

/**
 * Lightweight notices for things that actually happened: a plan was
 * recomputed, a region loaded, an approval recorded, an input is missing.
 * Nothing here is ever raised on a timer or to simulate activity.
 *
 * Warnings and errors stay long enough to read, and every toast can be
 * dismissed. They are announced politely; the underlying state is always on
 * screen elsewhere too, so a missed toast never hides information.
 */
export type ToastTone = "info" | "success" | "warning" | "error";

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

const LIFETIME_MS: Record<ToastTone, number> = { info: 3200, success: 3600, warning: 7500, error: 9000 };
const ICON = { info: Info, success: CheckCircle2, warning: AlertTriangle, error: AlertTriangle };

const ToastContext = React.createContext<(message: string, tone?: ToastTone) => void>(() => {});

export const useToast = () => React.useContext(ToastContext);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const next = React.useRef(0);

  const dismiss = React.useCallback((id: number) => setToasts(list => list.filter(t => t.id !== id)), []);
  const push = React.useCallback((message: string, tone: ToastTone = "info") => {
    setToasts(list => {
      // The same message twice in a row is one event seen twice: refresh it.
      const kept = list.filter(t => t.message !== message).slice(-3);
      return [...kept, { id: ++next.current, tone, message }];
    });
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="gn-toasts" role="status" aria-live="polite">
        {toasts.map(toast => <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />)}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = React.useState(false);
  React.useEffect(() => {
    if (paused) return;
    const timer = setTimeout(() => onDismiss(toast.id), LIFETIME_MS[toast.tone]);
    return () => clearTimeout(timer);
  }, [paused, toast, onDismiss]);
  const Icon = ICON[toast.tone];
  return (
    <div
      className={`gn-toast gn-toast--${toast.tone} gn-enter`}
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}
    >
      <Icon size={15} aria-hidden="true" />
      <span>{toast.message}</span>
      <button type="button" onClick={() => onDismiss(toast.id)} aria-label="Dismiss notification"><X size={13} /></button>
    </div>
  );
}
