import { API_BASE_URL } from "../api/api";
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";


export default function LoginPage() {
  const [name, setName] = useState('');
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();

    const login = async(e: React.FormEvent) => {
      
      e.preventDefault();

      if (!name || !password) {
        setError("Please fill in both fields.");
        return;
      }
      try{
        const response = await fetch(`${API_BASE_URL}/api/user/login`, {
          credentials: "include",
          method: "POST",
          headers: {
            'Content-Type': "application/json"
          },
          body: JSON.stringify({
              email: `${name}`,
              password: `${password}`
          })
        })

        if (response.ok){
          navigate('/Dashboard');
        }
        else{
          console.log(name)
        }
      }
      catch (error){
        console.log(error);
        setError("An error occurred. Please try again later.");
      }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f172a]">
      <div className="bg-[#1e293b] p-8 rounded-2xl shadow-lg w-full max-w-md">
        <h2 className="text-2xl font-bold text-center text-white mb-6">
          Welcome Back
        </h2>
        <form className="space-y-6"
          onSubmit={login}>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Email
            </label>
            <input
              type="email"
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-md bg-[#334155] text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Password
            </label>
            <input
              type="password"
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-md bg-[#334155] text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button
            type="submit"
            className="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-700 rounded-md text-white font-medium"
          >
            Sign In
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-gray-400">
          Don’t have an account? {" "}
          <a href="#" className="text-indigo-400 hover:text-indigo-300">
            Sign Up
          </a>
        </p>
      </div>
    </div>
  );
};


