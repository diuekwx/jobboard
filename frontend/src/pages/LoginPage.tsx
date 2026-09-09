import { useState } from "react";

import { API_BASE_URL } from "../api/api";

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  const handleGoogleSignIn = async () => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/gmail/auth/google`, {
        method: "GET",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Google sign-in could not be started");

      const data: { auth_url?: string } = await response.json();
      if (!data.auth_url) throw new Error("Google sign-in URL was missing");

      window.location.assign(data.auth_url);
    } catch {
      setError("Couldn't start Google sign-in. Try again shortly.");
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

        <div className="stack-2">
          {error && <p className="notice">! {error}</p>}
          <button onClick={handleGoogleSignIn} className="btn btn--solid btn--block">
            Log in with Google
          </button>
          <p className="login__foot">
            Your Google account is used to sign in and connect Gmail.
          </p>
        </div>
      </div>
    </div>
  );
}
