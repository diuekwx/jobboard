import React, { useState, useEffect } from "react";
import { API_BASE_URL } from "../api/api";
interface DateInputProps {
  onDateChange: (date: string) => void;
};

interface DateResponse {
  date: string | null;
};


const DateInput: React.FC<DateInputProps> = ({ onDateChange }) => {
  const [date, setDate] = useState("");


  useEffect(() => {
  
    const getDate = async () => {
        const response = await fetch(`${API_BASE_URL}/sync/start_date`, {
          method: "GET",
          credentials: "include"
        })

        const data: DateResponse = await response.json();
        console.log("data", data.date);
        if (data.date !== null){
          const formatted = data.date.slice(0, 10); 
          setDate(formatted);
          onDateChange(formatted);
        }
    } 
    getDate();

  }, [onDateChange]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setDate(newDate);
    onDateChange(newDate);
  };

  return (
    <div className="bg-gray-800 rounded-2xl shadow-md p-4 flex flex-col space-y-2">
      <label className="text-gray-300 text-sm font-medium">Select Date</label>
      <input
        type="date"
        value={date}
        onChange={handleChange}
        className="bg-gray-700 text-gray-100 px-3 py-2 rounded-lg border border-gray-600
                   focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                   transition"
      />
    </div>
  );
};

export default DateInput;
