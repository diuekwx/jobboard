import { useState, useEffect, useMemo } from "react";
import KanbanBoard from "../components/Kanban";
import { API_BASE_URL } from "../api/api";
import DateInput from "../components/DateInput";
import { paneFor, type Application } from "../types";

interface APIResponse {
  message: string;
  applications: Application[];
}

const Dashboard = () => {
  const [startDate, setStartDate] = useState("");
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");

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

  const refresh = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/gmail-service/fetch-applications`,
        {
          method: "GET",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        }
      );

      if (!response.ok) {
        console.error("Something went wrong");
        setNote("scan failed — try again");
        return;
      }

      const data: APIResponse = await response.json();
      setApps(data?.applications ?? []);
      setNote(data?.message ?? "");
    } catch (error) {
      console.error("Error fetching applications:", error);
      setNote("scan failed — try again");
    } finally {
      setLoading(false);
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

  const tally = useMemo(() => {
    const sent = apps.filter((a) => paneFor(a.status) === "sent").length;
    const active = apps.filter((a) => paneFor(a.status) === "process").length;
    const rejected = apps.filter((a) => paneFor(a.status) === "rejected").length;
    const total = apps.length;
    const responded = active + rejected;
    const rate = total ? Math.round((responded / total) * 100) : 0;
    return { sent, active, rejected, total, rate };
  }, [apps]);

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="wrap stack-4">
      <header className="stack-2">
        <div className="row row--between row--baseline">
          <span className="wordmark" style={{ fontSize: "2rem" }} aria-label="job">
            j<span className="redact" aria-hidden="true" />
            <span className="sr-only">o</span>b
          </span>
          <span className="eyebrow">dispatch log &middot; {today}</span>
        </div>
        <hr className="rule" />
      </header>

      <section className="receipt stack-1" aria-label="Summary">
        <div className="lead">
          <span>Total dispatched</span>
          <span className="lead__f" />
          <span className="lead__v">{tally.total}</span>
        </div>
        <div className="lead">
          <span>Sent</span>
          <span className="lead__f" />
          <span className="lead__v">{tally.sent}</span>
        </div>
        <div className="lead">
          <span>In process</span>
          <span className="lead__f" />
          <span className="lead__v">{tally.active}</span>
        </div>
        <div className="lead">
          <span>Rejected</span>
          <span className="lead__f" />
          <span className="lead__v">{tally.rejected}</span>
        </div>
        <hr className="hair" />
        <div className="lead lead--strong">
          <span>Response rate</span>
          <span className="lead__f" />
          <span className="lead__v">{tally.rate}%</span>
        </div>
      </section>

      <section className="stack-1">
        <span className="eyebrow">Controls</span>
        <div className="row">
          <span className="eyebrow">Start date</span>
          <DateInput onDateChange={(date) => setStartDate(date)} />
          <button
            className="btn btn--solid"
            onClick={refresh}
            disabled={loading}
          >
            {loading ? "Refreshing" : "Refresh"}
          </button>
          <button className="btn" onClick={dateset} disabled={loading}>
            Sync by date
          </button>
          <span className="mono" style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            {startDate ? startDate : "no date set"}
          </span>
        </div>
      </section>

      <section className="stack-1">
        <div className="row row--between row--baseline">
          <span className="eyebrow">Pipeline</span>
          {note && (
            <span className="mono" style={{ fontSize: "0.72rem", color: "var(--muted)" }}>
              {note}
            </span>
          )}
        </div>
        <KanbanBoard apps={apps} loading={loading} />
      </section>
    </div>
  );
};

export default Dashboard;
