export type ApplicationStatus = "sent" | "process" | "rejected";

export interface Application {
  id: string;
  company?: string;
  role?: string | null;
  date: string;
  status: string;
  source?: string;
  needs_review?: boolean;
  permalink?: string | null;
  /** When the decline landed. Only set once an application is rejected. */
  rejected_at?: string | null;
}

/** Anything the backend has no pane for lands in "Sent". */
const PANE_BY_STATUS: Record<string, ApplicationStatus> = {
  sent: "sent",
  applied: "sent",
  process: "process",
  interview: "process",
  offer: "process",
  rejected: "rejected",
};

export const paneFor = (status: string): ApplicationStatus =>
  PANE_BY_STATUS[(status ?? "").toLowerCase()] ?? "sent";

/** Timestamps arrive as ISO dates or datetimes; the log shows the day only. */
export const dayOf = (value?: string | null): string =>
  (value ?? "").slice(0, 10);
