import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, CalendarDays, Image, Plus, Search } from "lucide-react";
import { useDemo } from "./store";
import {
  Badge,
  Dialog,
  Empty,
  Field,
  Form,
  Heading,
  Panel,
  Timeline,
  value,
} from "./ui";
import {
  dateKey,
  dateLabel,
  isCollector,
  isCoordinator,
  isResident,
  number,
  statuses,
  visibleRequests,
  type Request,
} from "./model";
import { operate, type Action } from "./operations";

export function RequestList({
  items,
  title,
  base,
  create = false,
}: {
  items: Request[];
  title: string;
  base: string;
  create?: boolean;
}) {
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [page, setPage] = useState(0);
  const filtered = items.filter(
    (r) =>
      (!status || r.status === status) &&
      [r.id, r.name, r.classification, r.address]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase()),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 6)),
    current = Math.min(page, pages - 1);
  return (
    <>
      <Heading
        title={title}
        text="Busca y consulta el estado de las solicitudes."
      >
        {create && (
          <Link className="btn primary" to="/solicitar">
            <Plus size={18} /> Nueva solicitud
          </Link>
        )}
      </Heading>
      <Panel>
        <div className="filters">
          <Field label="Buscar solicitudes">
            <div className="search">
              <Search size={17} />
              <input
                placeholder="Código, material o ubicación"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
            </div>
          </Field>
          <Field label="Estado">
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(0);
              }}
            >
              <option value="">Todos los estados</option>
              {statuses.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
        </div>
        {filtered.length ? (
          <>
            <div className="table-wrap">
              <table className="responsive-table">
                <thead>
                  <tr>
                    {[
                      "Solicitud",
                      "Material",
                      "Ubicación",
                      "Fecha",
                      "Horario",
                      "Estado",
                      "Acción",
                    ].map((t) => (
                      <th key={t}>{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(current * 6, current * 6 + 6).map((r) => (
                    <tr key={r.id}>
                      <td data-label="Solicitud">
                        <strong>{r.id}</strong>
                        <small>{r.name}</small>
                      </td>
                      <td data-label="Material">
                        <div className="material">
                          {r.photo ? (
                            <img src={r.photo} alt="Residuo" />
                          ) : (
                            <Image size={16} />
                          )}
                          <span>
                            {r.classification}
                            <small>{r.group}</small>
                          </span>
                        </div>
                      </td>
                      <td data-label="Ubicación">{r.address}</td>
                      <td data-label="Fecha">{dateLabel(r.created)}</td>
                      <td data-label="Horario">{r.preferred}</td>
                      <td data-label="Estado">
                        <Badge status={r.status} />
                      </td>
                      <td>
                        <Link
                          className="text-link"
                          to={base + "/solicitud/" + r.id}
                        >
                          Abrir <ArrowRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="line pagination">
              <small>
                {filtered.length} solicitudes · Página {current + 1} de {pages}
              </small>
              <div className="actions">
                <button
                  className="btn secondary"
                  disabled={!current}
                  onClick={() => setPage(current - 1)}
                >
                  Anterior
                </button>
                <button
                  className="btn secondary"
                  disabled={current + 1 >= pages}
                  onClick={() => setPage(current + 1)}
                >
                  Siguiente
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty>No hay solicitudes con estos filtros.</Empty>
        )}
      </Panel>
    </>
  );
}
const actionLabels: Record<Action["kind"], string> = {
  review: "Revisar solicitud",
  assign: "Asignar responsable",
  schedule: "Programar recolección",
  collect: "Registrar recolección",
  cancel: "Cancelar solicitud",
  correct: "Corregir recolección",
};
export function RequestDetail() {
  const { id } = useParams(),
    { state, actor, save } = useDemo(),
    [action, setAction] = useState<Action["kind"]>();
  const who = actor!,
    r = visibleRequests(state, who).find((item) => item.id === id),
    base = "/panel/" + who.role;
  if (!r)
    return (
      <>
        <Heading
          title="Acceso denegado"
          text="La solicitud no está disponible para este perfil."
        />
        <Link className="btn secondary" to={base}>
          Volver al panel
        </Link>
      </>
    );
  const staff = state.people.filter(
    (p) =>
      p.active &&
      p.role === (r.group === "Reciclable" ? "reciclador" : "huertero"),
  );
  const worker = state.people.find((p) => p.id === r.worker)?.name;
  const coordinator = state.people.find((p) => p.id === r.coordinator)?.name;
  const manage = who.role === "admin" || isCoordinator(who.role);
  const actions: Action["kind"][] = [];
  if (manage) {
    if (r.status === "Recibida") actions.push("review");
    if (["En revisión", "Asignada", "Programada"].includes(r.status))
      actions.push("assign");
    if (r.status === "Asignada" || r.status === "Programada")
      actions.push("schedule");
    if (r.status === "Programada") actions.push("collect");
    if (r.status !== "Cancelada" && r.status !== "Recolectada")
      actions.push("cancel");
    if (who.role === "admin" && r.status === "Recolectada")
      actions.push("correct");
  }
  const fields = [
    ["Solicitante", r.name],
    ["Teléfono", r.phone],
    ["Tipo de generador", r.generator],
    ["Sector", r.sector],
    ["Dirección", r.address],
    ["Referencias", r.references],
    ["Residuo", r.group],
    ["Clasificación confirmada", r.classification],
    ["Clasificación sugerida (demo)", r.ai],
    ["Descripción", r.description],
    ["Cantidad estimada", r.estimate && number(r.estimate) + " kg"],
    ["Horario preferido", r.preferred],
    ["Observaciones", r.notes],
    ["Responsable", worker],
    ["Coordinación", coordinator],
    ["Fecha de asignación", r.assignedAt && dateLabel(r.assignedAt)],
  ];
  const restricted = isCollector(who.role);
  return (
    <>
      <Link
        className="text-link"
        to={base + (restricted ? "/asignaciones" : "/solicitudes")}
      >
        Volver a {restricted ? "asignaciones" : "solicitudes"}
      </Link>
      <Heading title={r.id} text={"Recibida el " + dateLabel(r.created)}>
        <Badge status={r.status} />
      </Heading>
      {actions.length > 0 && (
        <div className="actions mb-5">
          {actions.map((a) => (
            <button
              key={a}
              onClick={() => setAction(a)}
              className={"btn " + (a === actions[0] ? "primary" : "secondary")}
            >
              {actionLabels[a]}
            </button>
          ))}
        </div>
      )}
      <div className="detail-grid">
        <div className="stack">
          <Panel title="Datos de la solicitud">
            {r.photo && !restricted && (
              <img
                className="upload-preview"
                src={r.photo}
                alt="Material de la solicitud"
              />
            )}
            <dl className="facts">
              {fields
                .filter(
                  ([k]) =>
                    !restricted ||
                    [
                      "Solicitante",
                      "Teléfono",
                      "Sector",
                      "Dirección",
                      "Referencias",
                      "Residuo",
                      "Clasificación confirmada",
                      "Horario preferido",
                      "Responsable",
                    ].includes(String(k)),
                )
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v || "—"}</dd>
                  </div>
                ))}
            </dl>
          </Panel>
          {r.schedule && (
            <Panel title="Programación">
              <p>
                {dateLabel(r.schedule.date)} · {r.schedule.time} · {worker}
              </p>
              <p>{r.schedule.notes}</p>
            </Panel>
          )}
          {r.collection && (
            <Panel title="Pesaje confirmado">
              <p>
                <strong>{number(r.collection.weight)} kg</strong> ·{" "}
                {r.collection.material} · {dateLabel(r.collection.date)}
              </p>
              <p>
                {r.collection.result} · {r.collection.notes}
              </p>
            </Panel>
          )}
        </div>
        <Panel title="Seguimiento">
          <Timeline
            events={
              restricted
                ? r.history.map((e) => ({ ...e, note: undefined }))
                : r.history
            }
            status={r.status}
          />
        </Panel>
      </div>
      {action && (
        <Dialog
          title={actionLabels[action]}
          onClose={() => setAction(undefined)}
        >
          <Form
            label="Confirmar"
            onSave={(d) => {
              const payload: Action =
                action === "review"
                  ? { kind: action }
                  : action === "assign"
                    ? { kind: action, worker: value(d, "worker") }
                    : action === "schedule"
                      ? {
                          kind: action,
                          date: value(d, "date"),
                          time: value(d, "time"),
                          notes: value(d, "notes"),
                        }
                      : action === "cancel"
                        ? { kind: action, notes: value(d, "notes") }
                        : {
                            kind: action,
                            date: value(d, "date"),
                            weight: Number(value(d, "weight")),
                            material: value(d, "material"),
                            result: value(d, "result"),
                            notes: value(d, "notes"),
                          };
              save(
                (s) => operate(s, who, r.id, payload),
                actionLabels[action] + ": guardado.",
              );
              setAction(undefined);
            }}
          >
            {action === "review" && (
              <p>
                Confirma que revisaste la categoría y los datos de contacto.
              </p>
            )}
            {action === "assign" && (
              <Field label="Responsable del colectivo">
                <select name="worker" required defaultValue={r.worker ?? ""}>
                  <option value="">Seleccionar responsable</option>
                  {staff.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {action === "schedule" && (
              <>
                <Field label="Responsable">
                  <input readOnly value={worker ?? ""} />
                </Field>
                <div className="form-grid">
                  <Field label="Fecha">
                    <input
                      name="date"
                      type="date"
                      min={dateKey()}
                      defaultValue={r.schedule?.date}
                      required
                    />
                  </Field>
                  <Field label="Hora">
                    <input
                      name="time"
                      type="time"
                      defaultValue={r.schedule?.time}
                      required
                    />
                  </Field>
                </div>
                <Field label="Observaciones">
                  <textarea name="notes" defaultValue={r.schedule?.notes} />
                </Field>
              </>
            )}
            {(action === "collect" || action === "correct") && (
              <>
                <p>
                  {r.id} · {r.name} · {worker} · Estimado{" "}
                  {r.estimate ? number(r.estimate) + " kg" : "sin dato"}
                </p>
                <div className="form-grid">
                  <Field label="Fecha real">
                    <input
                      name="date"
                      type="date"
                      max={dateKey()}
                      required
                      defaultValue={r.collection?.date ?? dateKey()}
                    />
                  </Field>
                  <Field label="Peso real (kg)">
                    <input
                      name="weight"
                      type="number"
                      min=".001"
                      step="any"
                      required
                      defaultValue={r.collection?.weight}
                    />
                  </Field>
                  <Field label="Material">
                    <input
                      name="material"
                      required
                      defaultValue={r.collection?.material ?? r.classification}
                    />
                  </Field>
                  <Field label="Resultado">
                    <select name="result" defaultValue={r.collection?.result}>
                      <option>Aprovechable</option>
                      <option>No aprovechable</option>
                    </select>
                  </Field>
                </div>
                <Field
                  label={
                    action === "correct"
                      ? "Motivo de corrección"
                      : "Observaciones"
                  }
                >
                  <textarea name="notes" required={action === "correct"} />
                </Field>
              </>
            )}
            {action === "cancel" && (
              <>
                <p>
                  Se cerrará la solicitud y se registrará el motivo en el
                  historial.
                </p>
                <Field label="Motivo de cancelación">
                  <textarea required name="notes" />
                </Field>
              </>
            )}
          </Form>
        </Dialog>
      )}
    </>
  );
}
export function Calendar({ items, base }: { items: Request[]; base: string }) {
  const { state } = useDemo(),
    [view, setView] = useState("Mes"),
    [selected, setSelected] = useState(dateKey());
  const date = new Date(selected + "T12:00:00"),
    month = date.getMonth(),
    year = date.getFullYear();
  const first = new Date(year, month, 1),
    offset = (first.getDay() + 6) % 7;
  const start =
    view === "Mes"
      ? new Date(year, month, 1 - offset)
      : view === "Semana"
        ? new Date(year, month, date.getDate() - ((date.getDay() + 6) % 7))
        : date;
  const count =
    view === "Mes"
      ? Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7
      : view === "Semana"
        ? 7
        : 1;
  const days = Array.from(
    { length: count },
    (_, i) =>
      new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
  const scheduled = items.filter(
    (r) => r.schedule && r.status === "Programada",
  );
  function shift(dir: number) {
    setSelected(
      dateKey(
        view === "Mes"
          ? new Date(year, month + dir, 1)
          : new Date(
              year,
              month,
              date.getDate() + dir * (view === "Semana" ? 7 : 1),
            ),
      ),
    );
  }
  return (
    <>
      <Heading
        title="Calendario"
        text="Consulta las próximas recolecciones programadas."
      />
      <Panel>
        <div className="line calendar-tools">
          <div className="actions">
            <button className="btn secondary" onClick={() => shift(-1)}>
              Anterior
            </button>
            <button
              className="btn secondary"
              onClick={() => setSelected(dateKey())}
            >
              Hoy
            </button>
            <button className="btn secondary" onClick={() => shift(1)}>
              Siguiente
            </button>
          </div>
          <strong>
            {view === "Mes"
              ? date.toLocaleDateString("es-CO", {
                  month: "long",
                  year: "numeric",
                })
              : dateLabel(dateKey(days[0])) +
                (count > 1 ? " – " + dateLabel(dateKey(days[count - 1])) : "")}
          </strong>
          <Field label="Vista">
            <select value={view} onChange={(e) => setView(e.target.value)}>
              {["Mes", "Semana", "Día"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className={"calendar " + (count === 1 ? "day" : "")}>
          {days.map((d) => {
            const key = dateKey(d),
              events = scheduled
                .filter((r) => r.schedule!.date === key)
                .sort((a, b) =>
                  a.schedule!.time.localeCompare(b.schedule!.time),
                );
            return (
              <section key={key} className={events.length ? "has-events" : ""}>
                <h3>
                  {d.toLocaleDateString("es-CO", {
                    weekday: "short",
                    day: "numeric",
                  })}
                </h3>
                {events.map((r) => (
                  <Link key={r.id} to={base + "/solicitud/" + r.id}>
                    <CalendarDays size={14} />{" "}
                    <strong>
                      {r.schedule!.time} · {r.id}
                    </strong>
                    <small>
                      {state.people.find((p) => p.id === r.worker)?.name} ·{" "}
                      {r.address} · {r.status}
                    </small>
                  </Link>
                ))}
              </section>
            );
          })}
        </div>
        {!scheduled.some((r) =>
          days.some((d) => dateKey(d) === r.schedule!.date),
        ) && <Empty>No hay actividades programadas en este periodo.</Empty>}
      </Panel>
    </>
  );
}
export function Profile() {
  const { state, actor, save } = useDemo(),
    person = state.people.find((p) => p.id === actor?.id)!;
  return (
    <>
      <Heading
        title={person.role === "negocio" ? "Mi establecimiento" : "Mi perfil"}
      />
      <Panel>
        <Form
          onSave={(d) =>
            save(
              (s) => ({
                ...s,
                people: s.people.map((p) =>
                  p.id === person.id
                    ? {
                        ...p,
                        name: value(d, "name"),
                        address: value(d, "address"),
                        availability: value(d, "availability"),
                      }
                    : p,
                ),
              }),
              "Perfil actualizado.",
            )
          }
        >
          <div className="form-grid">
            <Field
              label={
                person.role === "negocio"
                  ? "Nombre del establecimiento"
                  : "Nombre"
              }
            >
              <input name="name" required defaultValue={person.name} />
            </Field>
            <Field label="Teléfono">
              <input readOnly value={person.phone} />
            </Field>
            {isResident(person.role) && (
              <>
                <Field label="Dirección">
                  <input
                    name="address"
                    required
                    defaultValue={person.address}
                  />
                </Field>
                <Field label="Disponibilidad">
                  <select
                    name="availability"
                    defaultValue={person.availability}
                  >
                    {["Mañana", "Tarde", "Horario flexible"].map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                </Field>
              </>
            )}
          </div>
        </Form>
      </Panel>
    </>
  );
}
