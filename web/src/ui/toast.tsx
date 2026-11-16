import { useSyncExternalStore } from "react";

type Toast = { id: number; text: string; error?: boolean; action?: { label: string; run: () => void } };

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit(next: Toast[]): void {
  toasts = next;
  listeners.forEach((listener) => listener());
}

/** Message bref en bas d'écran, annoncé aux lecteurs d'écran. */
export function toast(text: string, options: Omit<Toast, "id" | "text"> = {}): void {
  const id = nextId++;
  emit([...toasts.slice(-2), { id, text, ...options }]);
  window.setTimeout(() => emit(toasts.filter((item) => item.id !== id)), options.action ? 7000 : 4000);
}

export function Toasts() {
  const items = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => toasts,
  );
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast${item.error ? " error" : ""}`}>
          <span>{item.text}</span>
          {item.action && (
            <button
              onClick={() => {
                item.action!.run();
                emit(toasts.filter((other) => other.id !== item.id));
              }}
            >
              {item.action.label}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
