import { useState } from "react";
import { post } from "../api";
import { Mark } from "../App";
import type { User } from "../types";

export default function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await post<User>("/api/auth/login", { email, password }));
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="panel" onSubmit={submit}>
        <div className="panel-head">
          <h1 style={{ display: "flex", alignItems: "center", gap: 10, margin: 0, font: "300 20px var(--font-light)" }}>
            <Mark /> HKY Estates
          </h1>
        </div>
        <div className="panel-body stack" style={{ gap: 14 }}>
          <p className="muted" style={{ margin: 0 }}>Fırsat ajanına giriş yapın.</p>
          <label className="field"><span>E-posta</span>
            <input className="input" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field"><span>Şifre</span>
            <input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <div className="notice bad" role="alert">{error}</div>}
          <button className="btn primary" disabled={busy}>{busy ? "Giriş yapılıyor…" : "Giriş yap"}</button>
        </div>
      </form>
    </div>
  );
}
