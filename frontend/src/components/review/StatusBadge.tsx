import type { PendingStatus } from "../../types";

const LABELS: Record<PendingStatus, string> = {
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
};

export function StatusBadge({ status }: { status: PendingStatus }) {
  return <span className={`badge status-badge status-${status}`}>{LABELS[status]}</span>;
}
