// Tüm istekler aynı kökene gider; oturum httpOnly çerezdedir ve frontend hiçbir gizli değer tutmaz.
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    return (first.msg ?? "Geçersiz değer").replace(/^Value error, /, "");
  }
  return status >= 500 ? "Sunucu hatası. Biraz sonra tekrar deneyin." : `İstek başarısız (${status}).`;
}

export async function api<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const init: RequestInit = {
    credentials: "same-origin",
    ...rest,
    headers: { "X-HKY-CSRF": "1", ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  };
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Sunucuya ulaşılamadı. Backend çalışıyor mu?");
  }
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") window.dispatchEvent(new Event("hky:unauthorized"));
    throw new ApiError(response.status, detailMessage(body, response.status));
  }
  return body as T;
}

export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });
