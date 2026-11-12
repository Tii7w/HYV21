import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, post } from "../api";
import { useApp, useEvents } from "../context";
import { dateTime } from "../format";
import type { Note } from "../types";

export default function Notifications() {
  const { setUnread } = useApp();
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ items: Note[]; unread: number }>("/api/notifications?limit=100")
      .then((r) => {
        setNotes(r.items);
        setUnread(r.unread);
      })
      .catch((e) => setError((e as Error).message));
  }, [setUnread]);

  useEffect(() => {
    load();
  }, [load]);
  useEvents((event) => event === "notification" && load());

  async function markRead(note: Note) {
    if (note.read) return;
    await post(`/api/notifications/${note.id}/read`);
    load();
  }

  const unread = notes?.filter((n) => !n.read).length ?? 0;
  return (
    <>
      <div className="title-row">
        <div>
          <h1>Bildirimler</h1>
          <p className="sub">{notes === null ? "Yükleniyor…" : `${unread} okunmamış · fırsat skoru eşiği aşıldığında bildirim oluşur.`}</p>
        </div>
        <div className="title-actions">
          <button className="btn" disabled={!unread} onClick={() => post("/api/notifications/read-all").then(load)}>Tümünü okundu say</button>
        </div>
      </div>
      {error && <div className="notice bad" role="alert">{error}</div>}
      <section className="panel" aria-label="Bildirim geçmişi">
        {notes?.length === 0 && <div className="panel-body"><div className="empty">Henüz bildirim yok. Agent eşiği aşan yeni bir fırsat bulduğunda burada görünür.</div></div>}
        {notes?.map((note) => (
          <div className="note-row" key={note.id}>
            <span className={`dot ${note.read ? "" : "info"}`} aria-label={note.read ? "Okundu" : "Okunmadı"} style={{ marginTop: 7 }} />
            <div>
              <strong>{note.title}</strong>
              <p>{note.body}</p>
              <span className="small muted">{dateTime(note.created_at)}</span>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
              {note.score_id && <Link className="btn sm" to={`/firsat/${note.score_id}`} onClick={() => markRead(note)}>İlanı İncele</Link>}
              {!note.read && <button className="btn ghost sm" onClick={() => markRead(note)}>Okundu</button>}
            </div>
          </div>
        ))}
      </section>
    </>
  );
}
