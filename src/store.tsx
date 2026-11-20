import {
  createContext,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { seed } from "./data";
import type { Actor, State } from "./model";

const key = "ecoconecta360-demo-v1";
const sessionKey = "ecoconecta360-profile";
function load<T>(storage: Storage, key: string, fallback: () => T): T {
  try {
    return JSON.parse(storage.getItem(key) ?? "null") ?? fallback();
  } catch {
    return fallback();
  }
}
interface Store {
  state: State;
  actor: Actor | null;
  flash: string;
  save: (change: (state: State) => State, message?: string) => void;
  login: (actor: Actor | null) => void;
  reset: () => void;
  notify: (message: string) => void;
}
const Context = createContext<Store | null>(null);
export const useDemo = () => useContext(Context)!;
export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(() => load(localStorage, key, seed));
  const [actor, setActor] = useState<Actor | null>(() =>
    load(sessionStorage, sessionKey, () => null),
  );
  const [flash, setFlash] = useState("");
  const timer = useRef<number | undefined>(undefined);
  function notify(message: string) {
    setFlash(message);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setFlash(""), 5500);
  }
  function save(change: (state: State) => State, message?: string) {
    const latest = load(localStorage, key, () => state);
    const next = change(latest);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      throw Error(
        "No hay espacio para guardar. Prueba con una fotografía más pequeña.",
      );
    }
    setState(next);
    if (message) notify(message);
  }
  function login(next: Actor | null) {
    if (next) sessionStorage.setItem(sessionKey, JSON.stringify(next));
    else sessionStorage.removeItem(sessionKey);
    setActor(next);
  }
  function reset() {
    save(seed, "Demostración reiniciada.");
    login(null);
  }
  return (
    <Context.Provider
      value={{ state, actor, flash, save, login, reset, notify }}
    >
      {children}
      <div className={flash ? "toast" : "sr-only"} role="status">
        {flash}
      </div>
    </Context.Provider>
  );
}
