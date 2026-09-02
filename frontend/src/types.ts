export type ApplicationStatus = "sent" | "process" | "rejected";

export interface Application {
  id: string;
  company?: string;
  role?: string | null;
  date: string;
  status: string;
  source?: string;
  needs_review?: boolean;
  /** When the decline landed. Only set once an application is rejected. */
  rejected_at?: string | null;
}

/** Anything the backend has no column for lands in "Application Sent". */
const COLUMN_BY_STATUS: Record<string, ApplicationStatus> = {
  sent: "sent",
  applied: "sent",
  process: "process",
  interview: "process",
  offer: "process",
  rejected: "rejected",
};

export const columnFor = (status: string): ApplicationStatus =>
  COLUMN_BY_STATUS[(status ?? "").toLowerCase()] ?? "sent";
