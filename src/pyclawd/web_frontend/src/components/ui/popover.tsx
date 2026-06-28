// Popover primitive in the shadcn/ui style, wrapping Radix Popover with themed
// content. Used by the project switcher and the two ref pickers.
import * as PopoverPrimitive from "@radix-ui/react-popover";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverAnchor = PopoverPrimitive.Anchor;

/** Themed popover panel, rendered in a portal with sensible defaults. */
export function PopoverContent({
  className,
  align = "start",
  sideOffset = 5,
  ...props
}: ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 flex max-h-[70vh] w-[380px] flex-col overflow-hidden rounded-lg border border-line bg-canvas shadow-[0_8px_28px_rgba(0,0,0,0.16)] outline-none",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}
