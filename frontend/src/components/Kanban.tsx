import React from "react";
import { API_BASE_URL } from "../api/api";
import KanbanCard from "./KanbanCard";
import { useState, useEffect } from "react";
import DateInput from "./DateInput";

const columns = [
  { id: "sent", title: "Application Sent" },
  { id: "process", title: "In-Process" },
  { id: "rejected", title: "Rejected" },
];

interface Applications {
  id: string,
  company?: string,
  date: string
  // retrieve status 
  status: "sent"| "process" | "rejected";
}

interface APIResponse {
  message: string;
  applications: Applications[];
}

type ChildProp = {
  date: string
}

const KanbanBoard: React.FC<ChildProp> = ({date}) => {
    const [apps, setApps] = useState<Applications[]>([]);
    const [listApps, setListApps] = useState<Applications[]>([]);
      useEffect(() => {
        console.log("fetching jobs")
        listAllJobs();
      }, []);

    const dateset = async () => {
      console.log("date", date)
      const respone = await fetch(`${API_BASE_URL}/sync/sync_time`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ day: date }),
      });

      const data = await respone.json();
      console.log("data", data)
    }


    const listAllJobs = async () => {
      const response = await fetch(`${API_BASE_URL}/job/list`, {
        method: "GET",
        credentials: "include"
      });

      const data: APIResponse = await response.json();
      console.log(listAllJobs);
      setApps(data?.applications ?? []);


    }
    
    // use date input to filter refresh
   const refresh = async () => {
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
      // add these to curr state
      setApps(data?.applications ?? []);
    } catch (error) {
      console.error("Error fetching applications:", error);
      setApps([]);
    }
  };
return (
  <>
    <button onClick={refresh}> refresh </button>
    <button onClick={dateset}> date</button>
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
      </>
  );
  
};

export default KanbanBoard;
