import { useEffect, useRef, useState, type ReactNode } from "react";
import { Inbox, Check, X } from "lucide-react";
import { Link } from "react-router-dom";
import { dateLabel, statuses, type Event, type Status } from "./model";
export function Brand() {
  return (
    <Link
      to="/"
      className="brand"
      aria-label="EcoConecta Villas de San Pablo, inicio"
    >
      <img
        src="/identidad/ecoconecta.png"
        alt="EcoConecta Villas de San Pablo"
      />
    </Link>
  );
}
export function Heading({
  title,
  text,
  children,
}: {
  title: string;
  text?: string;
  children?: ReactNode;
}) {
  return (
    <header className="heading">
      <div>
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {children}
    </header>
  );
}
export function Panel({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <Inbox size={24} />
      <p>{children}</p>
    </div>
  );
}
export function Badge({ status }: { status: Status }) {
  return (
    <span className={"badge status-" + statuses.indexOf(status)}>{status}</span>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      {label}
      {children}
    </label>
  );
}
export const value = (data: FormData, key: string) =>
  String(data.get(key) ?? "").trim();
export function Form({
  children,
  onSave,
  label = "Guardar cambios",
}: {
  children: ReactNode;
  onSave: (data: FormData) => void | Promise<void>;
  label?: string;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <form
      className="form"
      onSubmit={async (e) => {
        e.preventDefault();
        if (busy) return;
        setBusy(true);
        setError("");
        try {
          await onSave(new FormData(e.currentTarget));
        } catch (cause) {
          setError((cause as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button className="btn primary" disabled={busy}>
        {busy ? "Guardando…" : label}
      </button>
    </form>
  );
}
export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="line">
        <h2 id="dialog-title">{title}</h2>
        <button className="icon-button" aria-label="Cerrar" onClick={onClose}>
          <X />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Timeline({
  events,
  status,
}: {
  events: Event[];
  status?: Status;
}) {
  return (
    <ol className="timeline">
      {events.map((e, i) => (
        <li key={i}>
          <span>
            <Check size={14} />
          </span>
          <div>
            <strong>{e.title}</strong>
            <small>
              {dateLabel(e.at)} · {e.by}
            </small>
            {e.note && <p>{e.note}</p>}
          </div>
        </li>
      ))}
      {status &&
        status !== "Cancelada" &&
        statuses.slice(statuses.indexOf(status) + 1, 5).map((s) => (
          <li className="future" key={s}>
            <span />
            <div>{s}</div>
          </li>
        ))}
    </ol>
  );
}
export async function imageData(file: FormDataEntryValue | null) {
  if (!(file instanceof File) || !file.size) return undefined;
  if (
    !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
    file.size > 8_000_000
  )
    throw Error("Selecciona una imagen JPG, PNG o WebP de hasta 8 MB.");
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, 960 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas
      .getContext("2d")!
      .drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/webp", 0.8);
  } finally {
    bitmap.close();
  }
}
