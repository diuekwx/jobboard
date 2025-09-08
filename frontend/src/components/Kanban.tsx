import React from "react";
import { API_BASE_URL } from "../api/api";
import KanbanCard from "./KanbanCard";
import { useState, useEffect } from "react";

const columns = [
  { id: "sent", title: "Application Sent" },
  { id: "process", title: "In-Process" },
  { id: "rejected", title: "Rejected" },
];

interface Applications {
  id: string,
  company?: string,
  date: string
  status: "sent"| "process" | "rejected";
}

interface APIResponse {
  message: string;
  applications: Applications[];
}

const KanbanBoard: React.FC = () => {
    const [apps, setApps] = useState<Applications[]>([]);
      useEffect(() => {
        console.log("sending req")
        getMessages();
      }, []);
    
   const getMessages = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/gmail-service/fetch-applications`, {
        method: "GET",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        console.error("Something went wrong");
        return;
      }

      const data: APIResponse = await response.json();
      console.log("data:", data);

      setApps(data?.applications ?? []);
    } catch (error) {
      console.error("Error fetching applications:", error);
      setApps([]);
    }
  };
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
            {apps.
            filter(item => item.status === col.id)
            .map(item => (
              <KanbanCard 
                key={item.id}
                id={item.id}
                company={item.company}
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
