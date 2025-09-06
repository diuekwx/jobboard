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

const handleGoogleSignIn = async () => {
  const response = await fetch(`${API_BASE_URL}/gmail/auth/google`, {
    method: "GET",
    credentials: "include"
  });
  if (!response.ok){
    console.log("error");
    return;
  }
  const data = await response.json();
  if (data.auth_url){
    await new Promise(res => setTimeout(res, 500));
    window.location.href = data.auth_url;
  }
};
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
        <button
          onClick={handleGoogleSignIn}
          className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white font-medium py-2 px-4 rounded-lg transition"
        >
          <svg
            className="w-5 h-5"
            viewBox="0 0 533.5 544.3"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              fill="currentColor"
              d="M533.5 278.4c0-18.5-1.5-37.3-4.8-55.4H272v104.9h147.6c-6.3 34.4-25 63.6-53.5 83.3v68h86.6c50.7-46.7 80-115.3 80-200.8z"
            />
            <path
              fill="currentColor"
              d="M272 544.3c72.6 0 133.6-24.1 178.1-65.2l-86.6-68c-24.1 16.2-55 25.8-91.5 25.8-70.3 0-129.9-47.6-151.2-111.5H32.2v69.9C76.9 486 167.5 544.3 272 544.3z"
            />
            <path
              fill="currentColor"
              d="M120.8 325.4c-11.1-32.7-11.1-68.5 0-101.2V154.3H32.2c-43.7 86.9-43.7 188.9 0 275.8l88.6-69.7z"
            />
            <path
              fill="currentColor"
              d="M272 107.7c39.5 0 75 13.6 103 40.3l77.1-77.1C405.6 24.1 344.6 0 272 0 167.5 0 76.9 58.3 32.2 154.3l88.6 69.9c21.3-63.9 80.9-111.5 151.2-111.5z"
            />
          </svg>
          Sign in with Google
        </button>
      </div>
    </div>
  );
};


