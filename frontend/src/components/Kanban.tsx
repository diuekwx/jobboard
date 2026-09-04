import React, { useState } from "react";
import KanbanCard from "./KanbanCard";
import {
  paneFor,
  stageRank,
  type Application,
  type ApplicationStatus,
} from "../types";

const columns: { id: ApplicationStatus; title: string }[] = [
  { id: "sent", title: "Sent" },
  { id: "process", title: "In Process" },
  { id: "rejected", title: "Rejected" },
];

type KanbanBoardProps = {
  apps: Application[];
  loading?: boolean;
};

type PaneProps = {
  title: string;
  status: ApplicationStatus;
  entries: Application[];
  loading?: boolean;
};

const pad2 = (n: number) => String(n).padStart(2, "0");

const FAR_FUTURE = 8.64e15; // sorts undated entries last

/**
 * In Process is the pane with a clock on it, so it leads with whatever is due
 * soonest. An entry with no date sits below the dated ones, furthest-along
 * stage first. The other panes keep the order the backend sent.
 */
const orderFor = (
  status: ApplicationStatus,
  entries: Application[]
): Application[] => {
  if (status !== "process") return entries;
  const dueAt = (a: Application) => {
    const at = a.next_event?.at;
    const parsed = at ? new Date(at).getTime() : NaN;
    return Number.isNaN(parsed) ? FAR_FUTURE : parsed;
  };
  return [...entries].sort(
    (a, b) => dueAt(a) - dueAt(b) || stageRank(b.status) - stageRank(a.status)
  );
};

const SKELETON_ROWS = [
  ["58%", "36%"],
  ["44%", "28%"],
  ["66%", "40%"],
  ["38%", "24%"],
  ["52%", "32%"],
];

const PaneLoading = () => (
  <div className="pane__loading" role="status" aria-label="Receiving">
    {SKELETON_ROWS.map(([a, b], i) => (
      <div className="skel" key={i} style={{ animationDelay: `${i * 90}ms` }}>
        <span className="skel__bar" style={{ width: a }} />
        <span className="skel__bar skel__bar--sub" style={{ width: b }} />
      </div>
    ))}
  </div>
);

const Pane = ({ title, status, entries, loading }: PaneProps) => {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const ordered = orderFor(status, entries);
  const shown = q
    ? ordered.filter(
        (e) =>
          (e.company ?? "").toLowerCase().includes(q) ||
          (e.role ?? "").toLowerCase().includes(q) ||
          e.status.toLowerCase().includes(q) ||
          e.date.includes(q)
      )
    : ordered;

  return (
    <section className="pane">
      <header className="pane__head">
        <span className="eyebrow">{title}</span>
        <span className="pane__count">
          {loading
            ? "··"
            : q
            ? `${pad2(shown.length)}/${pad2(entries.length)}`
            : pad2(entries.length)}
        </span>
      </header>

      <div className="pane__search">
        <span className="pane__search-mark" aria-hidden="true">
          /
        </span>
        <input
          type="text"
          className="pane__search-input"
          placeholder="filter"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label={`Filter ${title}`}
          disabled={loading}
        />
      </div>

      <div className="pane__body">
        {loading ? (
          <PaneLoading />
        ) : shown.length === 0 ? (
          <p className="pane__empty eyebrow">{q ? "no match" : "no entries"}</p>
        ) : (
          shown.map((item, idx) => (
            <KanbanCard
              key={item.id}
              id={item.id}
              company={item.company}
              role={item.role}
              date={item.date}
              status={status}
              stage={item.status}
              index={idx}
              permalink={item.permalink}
              needsReview={item.needs_review}
              rejectedAt={item.rejected_at}
              nextEvent={item.next_event}
            />
          ))
        )}
      </div>
    </section>
  );
};

const KanbanBoard: React.FC<KanbanBoardProps> = ({ apps, loading }) => {
  return (
    <div className="panes">
      {columns.map((col) => (
        <Pane
          key={col.id}
          title={col.title}
          status={col.id}
          loading={loading}
          entries={apps.filter((item) => paneFor(item.status) === col.id)}
        />
      ))}
    </div>
  );
};

export default KanbanBoard;
