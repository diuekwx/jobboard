import {
  dayOf,
  daysUntil,
  momentOf,
  stageLabel,
  type ApplicationEvent,
  type ApplicationStatus,
} from "../types";

interface KanbanCardProps {
  id: string;
  company?: string;
  role?: string | null;
  date: string;
  status: ApplicationStatus;
  /** The raw backend status, which carries the stage inside "In Process". */
  stage: string;
  index: number;
  permalink?: string | null;
  needsReview?: boolean;
  rejectedAt?: string | null;
  nextEvent?: ApplicationEvent | null;
}

/** "in 7d" / "tomorrow" / "today" / "4d ago" — the countdown that makes the
 *  In Process pane worth scanning. */
const countdown = (at?: string | null): string => {
  const days = daysUntil(at);
  if (days === null) return "";
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  return days > 0 ? `in ${days}d` : `${-days}d ago`;
};

const KanbanCard = ({
  id,
  company,
  role,
  date,
  status,
  stage,
  index,
  permalink,
  needsReview,
  rejectedAt,
  nextEvent,
}: KanbanCardProps) => {
  const name = company || "—";
  const closed = status === "rejected" ? dayOf(rejectedAt) : "";
  const label = status === "process" ? stageLabel(stage) : "";
  const when = nextEvent?.at ? momentOf(nextEvent.at) : "";
  const due = countdown(nextEvent?.at);

  return (
    <div
      className={`entry entry--${status}${needsReview ? " entry--review" : ""}`}
      style={{ animationDelay: `${Math.min(index, 14) * 26}ms` }}
    >
      <span className="entry__idx">{String(index + 1).padStart(3, "0")}</span>

      <span className="entry__co">
        {permalink ? (
          <a
            href={permalink}
            target="_blank"
            rel="noreferrer"
            className="entry__colink"
            title={
              needsReview
                ? "Auto-guessed from the email — open it in Gmail to verify"
                : "Open the source email in Gmail"
            }
          >
            {name} ↗
          </a>
        ) : (
          name
        )}
        {needsReview && (
          <span
            className="entry__flag"
            title="Company/role was auto-guessed from the email — please verify"
          >
            {" "}
            ?
          </span>
        )}
      </span>

      <span className="entry__meta" title={id}>
        {role ? `${role} · ` : ""}applied {dayOf(date)}
        {closed ? ` · closed ${closed}` : ""}
      </span>

      {label && (
        <span className="entry__stage">
          <span className="tag">{label}</span>
          {when && (
            <span
              className={`entry__when${
                nextEvent?.past ? " entry__when--past" : ""
              }`}
              title={nextEvent?.title}
            >
              {when}
              {due ? ` · ${due}` : ""}
            </span>
          )}
          {!when && <span className="entry__when">no date given</span>}
        </span>
      )}
    </div>
  );
};

export default KanbanCard;
