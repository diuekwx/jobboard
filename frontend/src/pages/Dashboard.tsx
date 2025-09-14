import KanbanBoard from "../components/Kanban";
import { API_BASE_URL } from "../api/api";
import DateInput from "../components/DateInput";
import { useState, useEffect } from "react";

interface Applications {
  id: string;
  company?: string;
  date: string;
  status: "sent" | "process" | "rejected";
}

interface APIResponse {
  message: string;
  applications: Applications[];
}

const Dashboard = () => {
  const [startDate, setStartDate] = useState("");
  const [apps, setApps] = useState<Applications[]>([]);

  useEffect(() => {
    listAllJobs();
  }, []);

  const listAllJobs = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/job/list`, {
        method: "GET",
        credentials: "include",
      });

      const data: APIResponse = await response.json();
      setApps(data?.applications ?? []);
    } catch (error) {
      console.error("Error fetching jobs:", error);
      setApps([]);
    }
  };
  // pass date next to check
  const refresh = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/gmail-service/fetch-applications`, {
        method: "GET",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        console.error("Something went wrong");
        return;
      }

      const data: APIResponse = await response.json();
      setApps(data?.applications ?? []);
    } catch (error) {
      console.error("Error fetching applications:", error);
      setApps([]);
    }
  };

  const dateset = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/sync/sync_time`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day: startDate }),
      });

      const data = await response.json();
      console.log("Date sync response:", data);
    } catch (error) {
      console.error("Error syncing by date:", error);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <h1 className="text-3xl font-bold mb-6">Dashboard</h1>

      <div className="flex flex-col md:flex-row items-center gap-4 mb-6">
        <p className="font-bold"> Start Date: </p> <DateInput onDateChange={(date) => setStartDate(date)} />

        <button
          onClick={refresh}
          className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded-lg shadow transition duration-150"
        >
          Refresh
        </button>

        <button
          onClick={dateset}
          className="bg-green-600 hover:bg-green-700 text-white font-semibold py-2 px-6 rounded-lg shadow transition duration-150"
        >
          Sync by Date
        </button>

        <span className="text-gray-400 text-sm ml-2">
          {startDate ? `Selected: ${startDate}` : "No date selected"}
        </span>
      </div>

      {/* Pass apps to Kanban */}
      <KanbanBoard apps={apps} />
    </div>
  );
};

export default Dashboard;
