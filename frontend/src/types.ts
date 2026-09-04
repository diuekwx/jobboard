export type ApplicationStatus = "sent" | "process" | "rejected";

/** A dated thing an application is waiting on. */
export interface ApplicationEvent {
  /** "interview" | "assessment" */
  type: string;
  title: string;
  /** ISO timestamp of the slot or deadline. */
  at: string | null;
  ends_at: string | null;
  /** The date has already gone by. */
  past: boolean;
}

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
  /** Soonest interview slot or assessment deadline, if the mail named one. */
  next_event?: ApplicationEvent | null;
}

/** Anything the backend has no pane for lands in "Sent". */
const PANE_BY_STATUS: Record<string, ApplicationStatus> = {
  sent: "sent",
  applied: "sent",
  process: "process",
  assessment: "process",
  interview: "process",
  offer: "process",
  rejected: "rejected",
};

export const paneFor = (status: string): ApplicationStatus =>
  PANE_BY_STATUS[(status ?? "").toLowerCase()] ?? "sent";

/** How far along an application is, for the In Process pane's own ordering. */
const STAGE_RANK: Record<string, number> = {
  process: 0,
  assessment: 1,
  interview: 2,
  offer: 3,
};

export const stageRank = (status: string): number =>
  STAGE_RANK[(status ?? "").toLowerCase()] ?? -1;

/** Short label for the stage badge. Empty for anything with no stage of its own. */
const STAGE_LABELS: Record<string, string> = {
  assessment: "assessment",
  interview: "interview",
  offer: "offer",
};

export const stageLabel = (status: string): string =>
  STAGE_LABELS[(status ?? "").toLowerCase()] ?? "";

/** Timestamps arrive as ISO dates or datetimes; the log shows the day only. */
export const dayOf = (value?: string | null): string =>
  (value ?? "").slice(0, 10);

/**
 * Day plus clock time, for a slot the email pinned to an hour.
 * A midnight timestamp is a date-only deadline, so it shows as just the day.
 */
export const momentOf = (value?: string | null): string => {
  if (!value) return "";
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return dayOf(value);
  const day = dayOf(at.toISOString());
  const [h, m] = [at.getUTCHours(), at.getUTCMinutes()];
  if (h === 0 && m === 0) return day;
  return `${day} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};

/** Whole days from today to `value`; negative once it has gone by. */
export const daysUntil = (value?: string | null): number | null => {
  if (!value) return null;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return null;
  const startOfDay = (d: Date) =>
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  return Math.round(
    (startOfDay(at) - startOfDay(new Date())) / 86_400_000
  );
};
