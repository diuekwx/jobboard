import KanbanBoard from "../components/Kanban";
import { API_BASE_URL } from "../api/api";
import DateInput from "../components/DateInput";
import { useState } from "react";

const Dashboard = () => {
  const [startDate, seteStartDate] = useState("");

  const ping = async () => {
    const response = await fetch(`${API_BASE_URL}/api/user/ping`, {
      method: "GET",
      credentials: "include"
    });
    const data = await response.json();
    if (data){
      console.log(data);
    }
  };

  const me = async () => {
    const response = await fetch(`${API_BASE_URL}/api/user/me`, {
      method: "GET",
      credentials: "include"
    });
    const data = await response.json();
    if (data){
      console.log(data);
    }
  }
  return (

    <div className="min-h-screen bg-gray-900 text-white p-6">
    <DateInput
      onDateChange={(date) => {
        console.log("User picked date:", date);
        seteStartDate(date);
      }}
    />
    <button onClick={ping}>
      PING
    </button>
    <button onClick={me}>
    ME
    </button>
      <h1 className="text-3xl font-bold mb-6">Dashboard</h1>
      <KanbanBoard date={startDate}/>
    </div>
  );
};

export default Dashboard;
