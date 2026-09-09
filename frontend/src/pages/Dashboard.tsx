import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import KanbanBoard from "../components/Kanban";
import { apiFetch } from "../api/api";
import DateInput from "../components/DateInput";
import { momentOf, paneFor, type Application } from "../types";

interface APIResponse {
  message: string;
  applications: Application[];
}

interface ScanJob {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  phase: string;
  progress: {
    discovered: number;
    fetched: number;
    classified: number;
    applied: number;
    deferred: number;
    failed: number;
  };
  message?: string | null;
  error?: string | null;
}

interface HistoryItem {
  id: string;
  kind: string;
  summary: string;
  at: string;
  source_url?: string | null;
  undoable: boolean;
  undone?: boolean;
}

const blankForm = { company: "", role: "", status: "applied" };

/** The editor deliberately mirrors the three dashboard lanes. */
const dashboardStatus = (status: string) => {
  const lane = paneFor(status);
  return lane === "sent" ? "applied" : lane;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const [startDate, setStartDate] = useState("");
  const [apps, setApps] = useState<Application[]>([]);
  const [scan, setScan] = useState<ScanJob | null>(null);
  const [note, setNote] = useState("");
  const [gmailConnected, setGmailConnected] = useState(true);
  const [archived, setArchived] = useState<Application[]>([]);
  const [selected, setSelected] = useState<Application | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blankForm);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [reviewIndex, setReviewIndex] = useState(0);
  const appliedRef = useRef(0);

  const listAllJobs = useCallback(async () => {
    try {
      const response = await apiFetch("/job/list");
      if (response.status === 401) {
        navigate("/");
        return;
      }
      if (!response.ok) {
        setNote("Could not refresh applications; showing the last loaded board");
        return;
      }

      const data: APIResponse = await response.json();
      setApps(data?.applications ?? []);
    } catch (error) {
      console.error("Error fetching jobs:", error);
      setNote("Could not refresh applications; showing the last loaded board");
    }
  }, [navigate]);

  const loadArchived = useCallback(async () => {
    const response = await apiFetch("/job/archived");
    if (response.ok) {
      const data: { applications: Application[] } = await response.json();
      setArchived(data.applications);
    }
  }, []);

  useEffect(() => {
    const loadAccount = async () => {
      const response = await apiFetch("/api/user/me");
      if (response.status === 401) {
        navigate("/");
        return;
      }
      if (response.ok) {
        const account: { gmail_connected: boolean } = await response.json();
        setGmailConnected(account.gmail_connected);
      }
    };
    void loadAccount();
    void listAllJobs();
    void loadArchived();
    const resumeScan = async () => {
      try {
        const response = await apiFetch("/gmail-service/scans/current");
        if (response.ok) {
          const current: ScanJob | null = await response.json();
          setScan(current);
          appliedRef.current = current?.progress.applied ?? 0;
          if (current?.message) setNote(current.message);
        }
      } catch (error) {
        console.error("Error fetching scan status:", error);
      }
    };
    void resumeScan();
  }, [listAllJobs, loadArchived, navigate]);

  const scanning = scan?.status === "queued" || scan?.status === "running";
  const scanId = scan?.id;
  const reviewApps = useMemo(() => apps.filter((app) => app.needs_review), [apps]);
  const reviewApp = reviewApps[reviewIndex] ?? reviewApps[0];

  useEffect(() => {
    setReviewIndex((index) => Math.min(index, Math.max(reviewApps.length - 1, 0)));
  }, [reviewApps.length]);

  useEffect(() => {
    if (!scanning || !scanId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const response = await apiFetch(`/gmail-service/scans/${scanId}`);
        if (response.status === 401) {
          navigate("/");
          return;
        }
        if (!response.ok || cancelled) return;
        const next: ScanJob = await response.json();
        if (next.progress.applied > appliedRef.current) {
          appliedRef.current = next.progress.applied;
          void listAllJobs();
        }
        setScan(next);
        if (next.message) setNote(next.message);
        else if (next.status === "failed") {
          setNote(`Scan failed; existing applications were kept${next.error ? ` · ${next.error}` : ""}`);
        }
        if (next.status === "completed" || next.status === "failed") {
          void listAllJobs();
        }
      } catch (error) {
        console.error("Error polling scan status:", error);
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 1250);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [listAllJobs, navigate, scanId, scanning]);

  const refresh = async () => {
    try {
      const response = await apiFetch("/gmail-service/scans", {
        method: "POST",
      });

      if (!response.ok) {
        const problem = await response.json().catch(() => null);
        setNote(problem?.detail ?? "scan failed — try again");
        return;
      }

      const data: ScanJob = await response.json();
      setScan(data);
      appliedRef.current = data.progress.applied;
      setNote(data.message ?? "scan queued");
    } catch (error) {
      console.error("Error fetching applications:", error);
      setNote("scan failed — try again");
    }
  };

  const dateset = async () => {
    try {
      const response = await apiFetch("/sync/sync_time", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day: startDate }),
      });

      const data = await response.json();
      console.log("Date sync response:", data);
    } catch (error) {
      console.error("Error syncing by date:", error);
    }
  };

  const beginGoogle = async () => {
    const response = await apiFetch("/gmail/auth/google");
    const data: { auth_url?: string } = await response.json();
    if (response.ok && data.auth_url) window.location.assign(data.auth_url);
    else setNote("Google connection could not be started");
  };

  const logout = async () => {
    const response = await apiFetch("/api/user/logout", { method: "POST" });
    if (response.ok) navigate("/");
  };

  const disconnect = async () => {
    const response = await apiFetch("/api/user/gmail/disconnect", { method: "POST" });
    if (response.ok) {
      setGmailConnected(false);
      setNote("Gmail disconnected; stored authorization removed");
    }
  };

  const deleteAccount = async () => {
    if (!window.confirm("Permanently delete your account and all application data?")) return;
    const response = await apiFetch("/api/user/me", {
      method: "DELETE",
      headers: { "X-Confirm-Account-Deletion": "delete" },
    });
    if (response.ok) navigate("/");
    else setNote("Account deletion was not completed");
  };

  const openNew = () => {
    setSelected(null);
    setCreating(true);
    setHistory([]);
    setForm(blankForm);
  };

  const openApplication = async (app: Application) => {
    setCreating(false);
    setSelected(app);
    setForm({
      company: app.company ?? "",
      role: app.role ?? "",
      status: dashboardStatus(app.status),
    });
    const response = await apiFetch(`/job/${app.id}/history`);
    if (response.ok) {
      const data: { history: HistoryItem[] } = await response.json();
      setHistory(data.history);
    }
  };

  const closeEditor = () => {
    setCreating(false);
    setSelected(null);
    setHistory([]);
  };

  const saveApplication = async (resolveReview = false) => {
    const path = creating
      ? "/job/create"
      : resolveReview
      ? `/job/${selected!.id}/review/correct`
      : `/job/${selected!.id}`;
    const response = await apiFetch(path, {
      method: creating ? "POST" : resolveReview ? "POST" : "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company: form.company,
        position: form.role || null,
        status: form.status,
      }),
    });
    if (response.ok) {
      closeEditor();
      await listAllJobs();
      setNote(resolveReview ? "Review resolved" : creating ? "Application added" : "Application updated");
    } else {
      const problem = await response.json().catch(() => null);
      setNote(problem?.detail ?? "Application could not be saved");
    }
  };

  const archiveSelected = async () => {
    if (!selected) return;
    const response = await apiFetch(`/job/${selected.id}/archive`, { method: "POST" });
    if (response.ok) {
      closeEditor();
      await Promise.all([listAllJobs(), loadArchived()]);
      setNote("Application archived");
    }
  };

  const restoreApplication = async (app: Application) => {
    const response = await apiFetch(`/job/${app.id}/restore`, { method: "POST" });
    if (response.ok) await Promise.all([listAllJobs(), loadArchived()]);
  };

  const undo = async (actionId: string) => {
    const response = await apiFetch(`/job/actions/${actionId}/undo`, { method: "POST" });
    if (response.ok) {
      await Promise.all([listAllJobs(), loadArchived()]);
      closeEditor();
      setNote("Change undone");
    }
  };

  const exportData = async () => {
    const response = await apiFetch("/job/export/data");
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "job-data-export.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const tally = useMemo(() => {
    const at = (status: string) =>
      apps.filter((a) => a.status?.toLowerCase() === status).length;
    const sent = apps.filter((a) => paneFor(a.status) === "sent").length;
    const active = apps.filter((a) => paneFor(a.status) === "process").length;
    const rejected = at("rejected");
    const withdrawn = at("withdrawn");
    const offers = at("offer");
    const accepted = at("accepted");
    const total = apps.length;
    const responded = active + rejected;
    const rate = total ? Math.round((responded / total) * 100) : 0;
    return {
      sent,
      active,
      rejected,
      total,
      rate,
      assessment: at("assessment"),
      interview: at("interview"),
      offers,
      accepted,
      withdrawn,
    };
  }, [apps]);

  /** The next thing actually on the calendar, across every application. */
  const upNext = useMemo(() => {
    const dated = apps
      .filter((a) => a.next_event?.at && !a.next_event.past)
      .sort(
        (a, b) =>
          new Date(a.next_event!.at!).getTime() -
          new Date(b.next_event!.at!).getTime()
      );
    return dated[0] ?? null;
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
          <div className="row">
            <span className="eyebrow">dispatch log &middot; {today}</span>
            <button className="btn btn--quiet" onClick={logout}>Log out</button>
          </div>
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
        {tally.assessment > 0 && (
          <div className="lead lead--sub">
            <span>Assessment</span>
            <span className="lead__f" />
            <span className="lead__v">{tally.assessment}</span>
          </div>
        )}
        {tally.interview > 0 && (
          <div className="lead lead--sub">
            <span>Interview</span>
            <span className="lead__f" />
            <span className="lead__v">{tally.interview}</span>
          </div>
        )}
        {tally.offers > 0 && (
          <div className="lead lead--sub"><span>Offers</span><span className="lead__f" /><span className="lead__v">{tally.offers}</span></div>
        )}
        {tally.accepted > 0 && (
          <div className="lead lead--sub"><span>Accepted</span><span className="lead__f" /><span className="lead__v">{tally.accepted}</span></div>
        )}
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
        {upNext && (
          <div className="lead lead--strong">
            <span>
              Up next &middot; {upNext.company ?? "—"}
              <span className="up-next__kind">
                {" "}
                {upNext.next_event?.type}
              </span>
            </span>
            <span className="lead__f" />
            <span className="lead__v">{momentOf(upNext.next_event?.at)}</span>
          </div>
        )}
      </section>

      {apps.length === 0 && !creating && (
        <section className="onboarding stack-1" aria-label="Getting started">
          <span className="eyebrow">Start here</span>
          <p>1. Add an application yourself, or connect Gmail.</p>
          <p>2. Set the earliest date to scan and choose Refresh.</p>
          <p>3. Correct any items marked for review before relying on the timeline.</p>
        </section>
      )}

      <section className="stack-1">
        <span className="eyebrow">Controls</span>
        <div className="row">
          <span className="eyebrow">Start date</span>
          <DateInput onDateChange={(date) => setStartDate(date)} />
          <button
            className="btn btn--solid"
            onClick={refresh}
            disabled={scanning}
          >
            {scanning ? "Scanning" : "Refresh"}
          </button>
          <button className="btn" onClick={dateset} disabled={scanning}>
            Sync by date
          </button>
          <span className="mono" style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            {startDate ? startDate : "no date set"}
          </span>
        </div>
        {tally.withdrawn > 0 && (
          <div className="lead lead--sub"><span>Withdrawn</span><span className="lead__f" /><span className="lead__v">{tally.withdrawn}</span></div>
        )}
        <div className="row account-actions">
          <button className="btn btn--solid" onClick={openNew}>Add application</button>
          <button className="btn" onClick={exportData}>Export data</button>
          <button className="btn" onClick={gmailConnected ? disconnect : beginGoogle}>
            {gmailConnected ? "Disconnect Gmail" : "Reconnect Gmail"}
          </button>
          <button className="btn btn--danger" onClick={deleteAccount}>Delete account</button>
        </div>
      </section>

      {(creating || selected) && (
        <section className="editor stack-2" aria-label="Application editor">
          <div className="row row--between">
            <span className="eyebrow">{creating ? "New application" : "Manage application"}</span>
            <button className="btn btn--quiet" onClick={closeEditor}>Close</button>
          </div>
          <div className="editor__grid">
            <label className="stack-1"><span className="eyebrow">Company</span>
              <input className="field" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
            </label>
            <label className="stack-1"><span className="eyebrow">Role</span>
              <input className="field" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </label>
            <label className="stack-1"><span className="eyebrow">Status</span>
              <select className="field" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option value="applied">Sent</option>
                <option value="process">In process</option>
                <option value="rejected">Rejected</option>
              </select>
            </label>
          </div>
          <div className="row">
            <button className="btn btn--solid" disabled={!form.company.trim()} onClick={() => saveApplication(Boolean(selected?.needs_review))}>
              {selected?.needs_review ? "Save correction" : "Save"}
            </button>
            {selected && <button className="btn" onClick={archiveSelected}>Archive</button>}
          </div>
          {selected && (
            <div className="stack-1">
              <span className="eyebrow">History</span>
              {history.map((item) => (
                <div className="history-row" key={item.id}>
                  <span>{item.summary}{item.undone ? ' · undone' : ''}</span>
                  <span className="mono">{item.at.slice(0, 16).replace('T', ' ')}</span>
                  {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Source ↗</a>}
                  {item.undoable && <button className="btn btn--quiet" onClick={() => undo(item.id)}>Undo</button>}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {reviewApp && (
        <section className="review-queue" aria-labelledby="review-queue-title">
          <div className="review-queue__head">
            <div>
              <span className="eyebrow" id="review-queue-title">Needs confirmation</span>
              <p>We filled this from an email. Check the company and role before relying on it.</p>
            </div>
            <span className="review-queue__count" aria-label={`${reviewIndex + 1} of ${reviewApps.length} items`}>
              {String(reviewIndex + 1).padStart(2, "0")} / {String(reviewApps.length).padStart(2, "0")}
            </span>
          </div>
          <div className="review-queue__record">
            <div>
              <strong>{reviewApp.company || "Company not identified"}</strong>
              <span>{reviewApp.role || "Role not identified"}</span>
            </div>
            <button className="btn btn--solid" onClick={() => openApplication(reviewApp)}>Review details</button>
          </div>
          {reviewApps.length > 1 && (
            <div className="review-queue__nav" aria-label="Review queue navigation">
              <button className="btn btn--quiet" disabled={reviewIndex === 0} onClick={() => setReviewIndex((index) => index - 1)}>Previous</button>
              <button className="btn btn--quiet" disabled={reviewIndex === reviewApps.length - 1} onClick={() => setReviewIndex((index) => index + 1)}>Next</button>
            </div>
          )}
        </section>
      )}

      <section className="stack-1">
        <div className="row row--between row--baseline">
          <span className="eyebrow">Pipeline</span>
          {note && (
            <span className="mono" style={{ fontSize: "0.72rem", color: "var(--muted)" }}>
              {scanning && scan
                ? `${scan.phase} · ${scan.progress.applied}/${scan.progress.discovered}`
                : note}
            </span>
          )}
        </div>
        <KanbanBoard apps={apps} onManage={openApplication} />
      </section>

      {archived.length > 0 && (
        <section className="stack-1">
          <span className="eyebrow">Archive · {archived.length}</span>
          {archived.map((app) => (
            <div className="history-row" key={app.id}>
              <span>{app.company} · {app.role || 'role unknown'}</span>
              <button className="btn btn--quiet" onClick={() => restoreApplication(app)}>Restore</button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
};

export default Dashboard;
