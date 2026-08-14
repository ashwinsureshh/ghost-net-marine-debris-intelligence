/**
 * shadcn/ui-style primitives, kept in one file because the set is small.
 *
 * Same conventions as shadcn: components own no colours of their own, only the
 * CSS variables declared in index.css, so light/dark is one class on <html> and
 * nothing needs a per-theme branch. Variants use class-variance-authority.
 */
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------- Button -- */

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        outline: "border border-border bg-transparent hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        warning: "bg-warning text-warning-foreground hover:bg-warning/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: {
        // 44px min touch target on the default and icon sizes.
        default: "h-11 px-4 py-2 sm:h-9",
        sm: "h-9 rounded-md px-3 text-xs",
        lg: "h-12 rounded-md px-6",
        icon: "size-11 sm:size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";

/* ---------------------------------------------------------------- Card -- */

export const Card = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("rounded-lg border border-border bg-card text-card-foreground", className)}
    {...props}
  />
);

export const CardHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col gap-1 px-4 py-3", className)} {...props} />
);

export const CardTitle = ({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("text-sm font-semibold tracking-tight", className)} {...props} />
);

export const CardDescription = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("text-xs text-muted-foreground", className)} {...props} />
);

export const CardContent = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-4 pb-4", className)} {...props} />
);

/* --------------------------------------------------------------- Badge -- */

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-tight transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/15 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-muted-foreground",
        success: "border-transparent bg-success/15 text-success",
        warning: "border-transparent bg-warning/20 text-warning",
        destructive: "border-transparent bg-destructive/15 text-destructive",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = ({ className, variant, ...props }: BadgeProps) => (
  <span className={cn(badgeVariants({ variant }), className)} {...props} />
);

/* --------------------------------------------------------------- Input -- */

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
        "placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Label = ({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label className={cn("text-xs font-medium text-muted-foreground", className)} {...props} />
);

/* ------------------------------------------------------------- Switch -- */

interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  "aria-describedby"?: string;
}

export const Switch = ({
  checked,
  onCheckedChange,
  id,
  disabled,
  ...rest
}: SwitchProps) => (
  <button
    type="button"
    role="switch"
    id={id}
    aria-checked={checked}
    disabled={disabled}
    onClick={() => onCheckedChange(!checked)}
    className={cn(
      "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-150",
      "disabled:cursor-not-allowed disabled:opacity-50",
      checked ? "bg-primary" : "bg-input",
    )}
    {...rest}
  >
    <span
      className={cn(
        "pointer-events-none block size-4 rounded-full bg-background shadow transition-transform duration-150",
        checked ? "translate-x-4.5" : "translate-x-0.5",
      )}
    />
  </button>
);

/* ------------------------------------------------------------ Skeleton -- */

export const Skeleton = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />
);

/* ----------------------------------------------------------- Separator -- */

export const Separator = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div role="separator" className={cn("h-px w-full bg-border", className)} {...props} />
);

/* --------------------------------------------------------------- Modal -- */

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  labelledBy?: string;
}

/** Focus-trapped dialog: Escape closes, Tab cycles, focus returns on close. */
export const Modal = ({ open, onClose, title, description, children }: ModalProps) => {
  const ref = React.useRef<HTMLDivElement>(null);
  const restoreTo = React.useRef<HTMLElement | null>(null);
  const titleId = React.useId();
  const descId = React.useId();

  React.useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;

    const focusable = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));

    focusable()[0]?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      restoreTo.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  // z-2000, not z-50: Leaflet gives its own panes z-index 400-800 and its
  // controls 800-1000, so anything below that renders *behind the map*.
  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className="relative z-10 w-full max-w-lg rounded-lg border border-border bg-card p-5 shadow-xl"
      >
        <h2 id={titleId} className="text-base font-semibold">
          {title}
        </h2>
        {description && (
          <p id={descId} className="mt-1 text-sm text-muted-foreground">
            {description}
          </p>
        )}
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
};

/* ---------------------------------------------------------- EmptyState -- */

export const EmptyState = ({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) => (
  <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
    <Icon className="size-8 text-muted-foreground/60" />
    <p className="text-sm font-medium">{title}</p>
    {children && <div className="max-w-sm text-xs text-muted-foreground">{children}</div>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);
