import { API_BASE_URL } from "../api/api";
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function LoginPage() {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();

  const login = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name || !password) {
      setError("Enter an email and a password.");
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/user/login`, {
        credentials: "include",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          credentials: "include",
        },
        body: JSON.stringify({
          email: `${name}`,
          password: `${password}`,
        }),
      });
      await response.json().catch(() => null);
      if (response.ok) {
        navigate("/dashboard");
      } else {
        setError("That email and password didn't match.");
      }
    } catch {
      setError("Couldn't reach the server. Try again shortly.");
    }
  };

  const handleGoogleSignIn = async () => {
    const response = await fetch(`${API_BASE_URL}/gmail/auth/google`, {
      method: "GET",
      credentials: "include",
    });
    if (!response.ok) {
      setError("Couldn't start Google sign-in.");
      return;
    }
    const data = await response.json();
    if (data.auth_url) {
      await new Promise((res) => setTimeout(res, 500));
      window.location.href = data.auth_url;
    }
  };

  return (
    <div className="login">
      <div className="login__card stack-3">
        <div className="stack-1">
          <span className="wordmark login__mark" aria-label="job">
            j
            <span className="redact redact--anim" aria-hidden="true" />
            <span className="sr-only">o</span>b
          </span>
          <span className="eyebrow" style={{ display: "block" }}>
            application tracker
          </span>
        </div>

        <hr className="rule" />

        <form className="stack-2" onSubmit={login}>
          <div className="stack-3">
            <label className="fieldset">
              <span className="eyebrow">Email</span>
              <input
                type="email"
                autoComplete="username"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="field"
              />
            </label>

            <label className="fieldset">
              <span className="eyebrow">Password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="field"
              />
            </label>
          </div>

          {error && <p className="notice">! {error}</p>}

          <button type="submit" className="btn btn--solid btn--block">
            Sign in
          </button>
        </form>

        <div className="stack-1">
          <hr className="hair" />
          <button onClick={handleGoogleSignIn} className="btn btn--block">
            Continue with Google
          </button>
          <p className="login__foot">
            No account yet?{" "}
            <a href="#" className="ulink">
              Create one
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
