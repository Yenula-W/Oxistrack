import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { CircleNotch } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-base font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-ink text-bg hover:bg-white",
        secondary: "border border-line-strong bg-surface-2 text-ink hover:bg-surface-3",
        ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
        danger: "bg-bad/90 text-white hover:bg-bad",
        outline: "border border-line-strong text-ink-2 hover:bg-surface-2 hover:text-ink",
      },
      size: { sm: "h-8 px-2.5 text-sm", md: "h-9 px-3.5", lg: "h-10 px-5", icon: "h-8 w-8" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
    if (asChild) return <Slot className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props}>{children}</Slot>;
    return (
      <button className={cn(buttonVariants({ variant, size }), className)} ref={ref} disabled={disabled || loading} {...props}>
        {loading && <CircleNotch className="animate-spin" />}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";
