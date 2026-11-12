import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, post } from "./api";
import { AppContext, type AppState, type EventHandler } from "./context";
import { STATUS_LABELS } from "./format";
import type { AppSettings, FoundEvent, Job, Note, User } from "./types";
import OpportunityPopup from "./components/OpportunityPopup";
import AgentCenter from "./pages/AgentCenter";
import FoundOpportunities from "./pages/FoundOpportunities";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";
import OpportunityDetail from "./pages/OpportunityDetail";
import Settings from "./pages/Settings";

const TOAST_MS = 12_000;
const POPUP_QUEUE_MAX = 50;
const FOUND_PATH = "/bulunan-firsatlar";

export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M6 17 16 8l10 9" fill="none" stroke="var(--accent)" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M10 15v9h12v-9" fill="none" stroke="var(--ink)" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M14 24v-5h4v5" fill="none" stroke="var(--ink)" strokeWidth="2" />
    </svg>
  );
}

function Toasts({ notes, dismiss }: { notes: Note[]; dismiss: (id: number) => void }) {
  return (
    <div className="toasts" aria-live="polite">
      {notes.map((note) => (
        <div className="toast" key={note.id} role="status">
          <h4>{note.title}</h4>
          <p>{note.body}</p>
          <div style={{ display: "flex", gap: 8 }}>
            {note.score_id && (
              <Link className="btn primary sm" to={`/firsat/${note.score_id}`} onClick={() => dismiss(note.id)}>
                İlanı İncele
              </Link>
            )}
            <button className="btn ghost sm" onClick={() => dismiss(note.id)}>Kapat</button>
          </div>
        </div>
      ))}
    </div>
  );
}

const foundLink = (isDemo: boolean) => (isDemo ? `${FOUND_PATH}?mod=demo` : FOUND_PATH);

function Shell({ state, newFound, lastFoundDemo, children }: { state: AppState; newFound: number; lastFoundDemo: boolean; children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);
  const job = state.liveJob;
  const running = job && ["running", "queued", "pausing", "stopping"].includes(job.status);

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand" style={{ padding: 0 }}>
          <Mark size={24} /> <span className="brand-name" style={{ fontSize: 17 }}>HKY Estates</span>
        </Link>
        <button className="btn sm" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>Menü</button>
      </header>
      <aside className={`sidebar${menuOpen ? " open" : ""}`} aria-label="Ana menü">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <Link to="/" className="brand">
            <Mark />
            <span>
              <span className="brand-name">HKY Estates</span>
              <span className="brand-scope">Fırsat Ajanı · V2</span>
            </span>
          </Link>
          {menuOpen && <button className="btn sm" onClick={() => setMenuOpen(false)}>Kapat</button>}
        </div>
        <NavLink to="/" end className="nav-link">Fırsatlar ve arama</NavLink>
        <NavLink to={foundLink(lastFoundDemo)} className="nav-link">
          Bulunan fırsatlar {newFound > 0 && <span className="nav-count num" aria-label={`${newFound} yeni fırsat`}>{newFound}</span>}
        </NavLink>
        <NavLink to="/agent" className="nav-link">Agent merkezi</NavLink>
        <NavLink to="/bildirimler" className="nav-link">
          Bildirimler {state.unread > 0 && <span className="nav-count num" aria-label={`${state.unread} okunmamış`}>{state.unread}</span>}
        </NavLink>
        {state.isAdmin && <NavLink to="/ayarlar" className="nav-link">Tarama ayarları</NavLink>}
        <div className="sidebar-foot">
          <div className="agent-mini">
            <span>
              Agent: <strong style={{ color: "var(--ink)" }}>{job ? STATUS_LABELS[job.status] ?? job.status : "Boşta"}</strong>
              {running && <span className="num"> · %{Math.round(job.progress)}</span>}
            </span>
            {running && <div className="progress"><div style={{ width: `${job.progress}%` }} /></div>}
          </div>
          <span>{state.user.email} · {state.user.role === "admin" ? "Yönetici" : "İzleyici"}</span>
          <button className="btn sm" onClick={state.logout}>Çıkış yap</button>
        </div>
      </aside>
      <main className="canvas">{children}</main>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [unread, setUnread] = useState(0);
  const [liveJob, setLiveJob] = useState<Job | null>(null);
  const [toasts, setToasts] = useState<Note[]>([]);
  const [publicSettings, setPublicSettings] = useState<AppState["publicSettings"]>(null);
  const [popupQueue, setPopupQueue] = useState<number[]>([]);
  const [newFound, setNewFound] = useState(0);
  const [lastFoundDemo, setLastFoundDemo] = useState(false);
  const handlers = useRef(new Set<EventHandler>());
  const popupEnabled = useRef(true);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    popupEnabled.current = publicSettings?.notifications.popup ?? true;
  }, [publicSettings]);

  // Sekmeye girince "yeni" sayacı sıfırlanır; herhangi bir sayfa geçişinde popup kapanır.
  useEffect(() => {
    if (location.pathname === FOUND_PATH) setNewFound(0);
    setPopupQueue([]);
  }, [location.pathname]);

  const closePopup = useCallback(() => setPopupQueue([]), []);
  const nextPopup = useCallback(() => setPopupQueue((q) => q.slice(1)), []);
  const openFoundList = useCallback((isDemo: boolean) => {
    setPopupQueue([]);
    navigate(foundLink(isDemo));
  }, [navigate]);

  useEffect(() => {
    api<User>("/api/auth/me").then(setUser).catch(() => setUser(null));
    const onUnauthorized = () => setUser(null);
    window.addEventListener("hky:unauthorized", onUnauthorized);
    return () => window.removeEventListener("hky:unauthorized", onUnauthorized);
  }, []);

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((n) => n.id !== id)), []);

  useEffect(() => {
    if (!user) return;
    api<{ unread: number }>("/api/notifications?limit=1").then((r) => setUnread(r.unread)).catch(() => undefined);
    api<Pick<AppSettings, "notifications" | "agent">>("/api/settings/public").then(setPublicSettings).catch(() => undefined);
    api<Job[]>("/api/agent/jobs?limit=1").then((jobs) => setLiveJob(jobs[0] ?? null)).catch(() => undefined);

    const source = new EventSource("/api/events");
    const deliver = (event: string) => (message: MessageEvent) => {
      const data = JSON.parse(message.data);
      if (event === "job.updated") setLiveJob(data as Job);
      if (event === "opportunity.found") {
        const found = data as FoundEvent;
        setLastFoundDemo(found.is_demo);
        if (window.location.pathname !== FOUND_PATH) setNewFound((count) => count + 1);
        if (popupEnabled.current) {
          setPopupQueue((q) => (q.includes(found.score_id) ? q : [...q, found.score_id].slice(0, POPUP_QUEUE_MAX)));
        }
      }
      if (event === "notification") {
        const note = data as Note;
        setUnread((count) => count + 1);
        // Fırsat bildirimleri ortadaki popup ile gösterilir; köşe bildirimi yalnızca diğerleri için.
        if (note.popup && !note.score_id) {
          // En fazla iki pop-up; geri kalanlar bildirim merkezinde ve menü sayacında görünür.
          setToasts((list) => [note, ...list].slice(0, 2));
          window.setTimeout(() => dismiss(note.id), TOAST_MS);
        }
        // Tarayıcı bildirimi yalnızca kullanıcı izin verdiyse ve ayar açıksa gösterilir.
        if (note.browser && "Notification" in window && Notification.permission === "granted") {
          const browserNote = new Notification(note.title, { body: note.body, tag: `hky-${note.listing_id}` });
          browserNote.onclick = () => {
            window.focus();
            if (note.score_id) navigate(`/firsat/${note.score_id}`);
          };
        }
      }
      handlers.current.forEach((handler) => handler(event, data));
    };
    for (const name of ["job.updated", "job.log", "notification", "opportunity.found"]) {
      source.addEventListener(name, deliver(name) as EventListener);
    }
    return () => source.close();
  }, [user, dismiss, navigate]);

  const state = useMemo<AppState | null>(() => {
    if (!user) return null;
    return {
      user, isAdmin: user.role === "admin", unread, setUnread, liveJob, publicSettings,
      subscribe: (handler) => {
        handlers.current.add(handler);
        return () => handlers.current.delete(handler);
      },
      logout: () => {
        post("/api/auth/logout").finally(() => setUser(null));
      },
    };
  }, [user, unread, liveJob, publicSettings]);

  if (user === undefined) return <div className="login muted">Yükleniyor…</div>;
  if (!state) return <Login onLogin={setUser} />;

  return (
    <AppContext.Provider value={state}>
      <Shell state={state} newFound={newFound} lastFoundDemo={lastFoundDemo}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path={FOUND_PATH} element={<FoundOpportunities />} />
          <Route path="/firsat/:scoreId" element={<OpportunityDetail />} />
          <Route path="/agent" element={<AgentCenter />} />
          <Route path="/bildirimler" element={<Notifications />} />
          <Route path="/ayarlar" element={state.isAdmin ? <Settings /> : <p>Bu ekran yalnızca yöneticiye açıktır.</p>} />
          <Route path="*" element={<p>Sayfa bulunamadı. <Link to="/">Ana sayfaya dön</Link></p>} />
        </Routes>
      </Shell>
      <Toasts notes={toasts} dismiss={dismiss} />
      <OpportunityPopup queue={popupQueue} onNext={nextPopup} onClose={closePopup} onOpenList={openFoundList} />
    </AppContext.Provider>
  );
}
