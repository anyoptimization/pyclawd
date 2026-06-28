// Button primitive in the shadcn/ui style (CVA variants + asChild via Radix Slot),
// themed to the Primer palette.
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-40 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-canvas border border-line hover:bg-panel2",
        accent: "bg-accent text-white border border-accent hover:opacity-90",
        ghost: "border border-transparent hover:bg-panel2",
      },
      size: {
        default: "h-[30px] px-2.5",
        sm: "h-[26px] px-2 text-xs",
        icon: "h-[30px] w-[30px]",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

/** A styled button; pass `asChild` to render the styling onto a child element. */
export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
