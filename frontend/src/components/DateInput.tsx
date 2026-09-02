import React, { useState, useEffect } from "react";
import { API_BASE_URL } from "../api/api";

interface DateInputProps {
  onDateChange: (date: string) => void;
}

interface DateResponse {
  date: string | null;
}

const DateInput: React.FC<DateInputProps> = ({ onDateChange }) => {
  const [date, setDate] = useState("");

  useEffect(() => {
    const getDate = async () => {
      const response = await fetch(`${API_BASE_URL}/sync/start_date`, {
        method: "GET",
        credentials: "include",
      });

      const data: DateResponse = await response.json();
      if (data.date !== null) {
        const formatted = data.date.slice(0, 10);
        setDate(formatted);
        onDateChange(formatted);
      }
    };
    getDate();
  }, [onDateChange]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setDate(newDate);
    onDateChange(newDate);
  };

  return (
    <input
      type="date"
      value={date}
      onChange={handleChange}
      className="field"
      aria-label="Sync start date"
    />
  );
};

export default DateInput;
