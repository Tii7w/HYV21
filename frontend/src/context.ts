import { createContext, useContext, useEffect, useRef } from "react";
import type { AppSettings, Job, User } from "./types";

export type EventHandler = (event: string, data: unknown) => void;

export type AppState = {
  user: User;
  isAdmin: boolean;
  unread: number;
  setUnread: (value: number) => void;
  liveJob: Job | null;
  publicSettings: Pick<AppSettings, "notifications" | "agent"> | null;
  subscribe: (handler: EventHandler) => () => void;
  logout: () => void;
};

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const value = useContext(AppContext);
  if (!value) throw new Error("AppContext eksik");
  return value;
}

/** Sunucudan gelen SSE olaylarına abone olur; handler her render'da güncel kalır. */
export function useEvents(handler: EventHandler): void {
  const { subscribe } = useApp();
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => subscribe((event, data) => ref.current(event, data)), [subscribe]);
}
