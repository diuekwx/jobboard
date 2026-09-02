import type { ApplicationStatus } from "../types";

interface KanbanCardProps {
  company?: string;
  role?: string | null;
  date: string;
  status: ApplicationStatus;
  rejectedAt?: string | null;
  needsReview?: boolean;
}

const formatDate = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
};

const KanbanCard = ({
  company,
  role,
  date,
  status,
  rejectedAt,
  needsReview,
}: KanbanCardProps) => {
  const rejected = status === "rejected";
  const applied = formatDate(date);
  const closed = formatDate(rejectedAt);

  return (
    <div
      className={`rounded-xl p-4 shadow-md transition-shadow duration-200 hover:shadow-lg ${
        rejected ? "bg-gray-800 border border-gray-600" : "bg-gray-700"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          className={`text-lg font-semibold ${
            rejected ? "text-gray-400 line-through decoration-gray-500" : ""
          }`}
        >
          {company ?? "Unknown company"}
        </h3>
        {needsReview && (
          <span
            title="Guessed from an email — worth a second look"
            className="shrink-0 rounded border border-gray-500 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-gray-400"
          >
            Review
          </span>
        )}
      </div>

      {role && <p className="mt-1 text-sm text-gray-300">{role}</p>}

      <p className="mt-2 text-sm text-gray-400">Applied: {applied ?? "—"}</p>
      {rejected && <p className="text-sm text-gray-500">Rejected: {closed ?? "—"}</p>}
    </div>
  );
};

export default KanbanCard;
