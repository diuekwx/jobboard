import React from "react";
import KanbanCard from "./KanbanCard";
import { columnFor, type Application, type ApplicationStatus } from "../types";

const columns: { id: ApplicationStatus; title: string }[] = [
  { id: "sent", title: "Application Sent" },
  { id: "process", title: "In-Process" },
  { id: "rejected", title: "Rejected" },
];

type KanbanBoardProps = {
  apps: Application[];
};

const KanbanBoard: React.FC<KanbanBoardProps> = ({ apps }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {columns.map((col) => {
        const cards = apps.filter((item) => columnFor(item.status) === col.id);

        return (
          <div
            key={col.id}
            className="bg-gray-800 rounded-2xl shadow-lg p-4 flex flex-col"
          >
            <h2 className="mb-4 flex items-baseline justify-between border-b border-gray-700 pb-2 text-xl font-semibold">
              {col.title}
              <span className="text-sm font-normal text-gray-400">{cards.length}</span>
            </h2>

            <div className="flex-1 space-y-3">
              {cards.length === 0 && (
                <p className="text-sm text-gray-500">Nothing here yet.</p>
              )}
              {cards.map((item) => (
                <KanbanCard
                  key={item.id}
                  company={item.company}
                  role={item.role}
                  date={item.date}
                  status={col.id}
                  rejectedAt={item.rejected_at}
                  needsReview={item.needs_review}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default KanbanBoard;
