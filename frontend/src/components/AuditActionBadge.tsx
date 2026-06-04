import { Pill, type PillTone } from "./ui";

const TONE_BY_ACTION: Record<string, PillTone> = {
  create:         "success",
  created:        "success",
  update:         "info",
  updated:        "info",
  delete:         "negative",
  deleted:        "negative",
  lock:           "warning",
  unlock:         "warning",
  status_changed: "warning",
};

export function AuditActionBadge({ action }: { action: string }) {
  return <Pill tone={TONE_BY_ACTION[action] ?? "neutral"}>{action}</Pill>;
}
