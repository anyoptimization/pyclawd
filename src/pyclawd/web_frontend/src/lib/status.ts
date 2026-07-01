// Mapping from a file's ChangeStatus to its display label and Primer color class.
import type { ChangeStatus } from "@/types";

/** A short human label for a change status (null = unchanged). */
export function statusLabel(status: ChangeStatus | null): string {
  switch (status) {
    case "A":
      return "added";
    case "M":
      return "modified";
    case "D":
      return "deleted";
    case "R":
      return "renamed";
    default:
      return "unchanged";
  }
}

/** Tailwind text-color class for a change status. */
export function statusColor(status: ChangeStatus | null): string {
  switch (status) {
    case "A":
      return "text-add";
    case "M":
      return "text-mod";
    case "D":
      return "text-del";
    case "R":
      return "text-ren";
    default:
      return "text-dim";
  }
}

/** Tailwind background class for the small square badge next to a file. */
export function statusBadge(status: ChangeStatus | null): string {
  switch (status) {
    case "A":
      return "bg-add";
    case "M":
      return "bg-mod";
    case "D":
      return "bg-del";
    case "R":
      return "bg-ren";
    default:
      return "bg-transparent ring-1 ring-inset ring-line";
  }
}
