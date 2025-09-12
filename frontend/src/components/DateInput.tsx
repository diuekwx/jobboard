import React, { useState } from "react";

interface DateInputProps {
  onDateChange: (date: string) => void; // send ISO string back
}

const DateInput: React.FC<DateInputProps> = ({ onDateChange }) => {
  const [date, setDate] = useState("");

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setDate(newDate);
    onDateChange(newDate); // pass up to parent
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
