import React from "react";
import KanbanCard from "./KanbanCard";

const columns = [
  { id: "sent", title: "Application Sent" },
  { id: "process", title: "In-Process" },
  { id: "rejected", title: "Rejected" },
];

interface Applications {
  id: string;
  company?: string;
  date: string;
  status: "sent" | "process" | "rejected";
}

type KanbanBoardProps = {
  apps: Applications[];
};

const KanbanBoard: React.FC<KanbanBoardProps> = ({ apps }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {columns.map((col) => (
        <div
          key={col.id}
          className="bg-gray-800 rounded-2xl shadow-lg p-4 flex flex-col"
        >
          <h2 className="text-xl font-semibold mb-4 border-b border-gray-700 pb-2">
            {col.title}
          </h2>
          <div className="flex-1 space-y-3">
            {apps
              .filter((item) => item.status === col.id)
              .map((item) => (
                <KanbanCard
                  key={item.id}
                  company={item.company}
                  id={item.id}
                  date={item.date}
                />
              ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default KanbanBoard;
