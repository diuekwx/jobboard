interface KanbanCardProps {
  id: string;
  company?: string;
  role?: string | null;
  date: string;
  status: "sent" | "process" | "rejected";
  index: number;
  permalink?: string | null;
  needsReview?: boolean;
}

const KanbanCard = ({
  id,
  company,
  role,
  date,
  status,
  index,
  permalink,
  needsReview,
}: KanbanCardProps) => {
  const name = company || "—";

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
        {role ? `${role} · ` : ""}applied {date}
      </span>
    </div>
  );
};

export default KanbanCard;
