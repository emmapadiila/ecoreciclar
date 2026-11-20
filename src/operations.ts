import {
  dateKey,
  isCoordinator,
  isResident,
  normalizePhone,
  roleGroup,
  visibleRequests,
  type Actor,
  type Intake,
  type Request,
  type State,
} from "./model.ts";

export type Action =
  | { kind: "review" }
  | { kind: "assign"; worker: string }
  | { kind: "schedule"; date: string; time: string; notes: string }
  | {
      kind: "collect" | "correct";
      date: string;
      weight: number;
      material: string;
      notes: string;
      result: string;
    }
  | { kind: "cancel"; notes: string };

export function createRequest(
  state: State,
  input: Intake,
  actor?: Actor,
  now = new Date(),
) {
  const phone = normalizePhone(input.phone);
  if (
    !/^3\d{9}$/.test(phone) ||
    ![
      input.name,
      input.sector,
      input.address,
      input.classification,
      input.description,
      input.preferred,
    ].every((value) => value.trim()) ||
    !["hogar", "negocio"].includes(input.generator) ||
    !["Reciclable", "Orgánico"].includes(input.group) ||
    (input.estimate !== undefined &&
      (!Number.isFinite(input.estimate) || input.estimate <= 0))
  )
    throw Error("Revisa los datos de contacto y del material.");
  const owner =
    actor && isResident(actor.role)
      ? state.people.find((p) => p.id === actor.id && p.active)
      : undefined;
  if (
    actor &&
    isResident(actor.role) &&
    (!owner || owner.role !== input.generator)
  )
    throw Error("El tipo de generador debe coincidir con el perfil.");
  const existing =
    owner ??
    state.people.find(
      (p) => p.phone === phone && p.role === input.generator && p.active,
    );
  const person = existing ?? {
    id: crypto.randomUUID(),
    name: input.name,
    phone,
    role: input.generator,
    active: true,
    pilot: false,
  };
  const prefix = "ECO-" + now.getFullYear() + "-";
  const sequence =
    Math.max(
      0,
      ...state.requests
        .filter((r) => r.id.startsWith(prefix))
        .map((r) => Number(r.id.slice(prefix.length))),
    ) + 1;
  const id = prefix + String(sequence).padStart(3, "0");
  const at = now.toISOString();
  const event = { title: "Recibida", at, by: input.name };
  const request: Request = {
    ...input,
    phone,
    id,
    owner: person.id,
    created: at,
    status: "Recibida",
    history: [event],
  };
  return {
    request,
    state: {
      ...state,
      people: existing ? state.people : [...state.people, person],
      requests: [request, ...state.requests],
      notices: [
        {
          ...event,
          title: "Nueva solicitud",
          id: crypto.randomUUID(),
          request: id,
          readBy: [],
        },
        ...state.notices,
      ],
    },
  };
}

export function operate(
  state: State,
  actor: Actor,
  id: string,
  action: Action,
  now = new Date(),
): State {
  const current = visibleRequests(state, actor).find((r) => r.id === id);
  if (!current || (actor.role !== "admin" && !isCoordinator(actor.role)))
    throw Error("Tu perfil no puede gestionar esta solicitud.");
  if (
    (current.status === "Cancelada" || current.status === "Recolectada") &&
    action.kind !== "correct"
  )
    throw Error("Esta solicitud ya está cerrada.");
  const at = now.toISOString();
  const next = { ...current };
  const worker = (id?: string) =>
    state.people.find(
      (p) =>
        p.id === id &&
        p.active &&
        p.role ===
          (current.group === "Reciclable" ? "reciclador" : "huertero") &&
        roleGroup(p.role) === current.group,
    );
  let note = "";
  let movements = state.movements;
  let title: string;
  switch (action.kind) {
    case "review":
      if (current.status !== "Recibida")
        throw Error("La solicitud ya fue revisada.");
      next.status = "En revisión";
      title = "Solicitud revisada";
      break;
    case "assign":
      if (
        !["En revisión", "Asignada", "Programada"].includes(current.status) ||
        !worker(action.worker)
      )
        throw Error(
          "Selecciona un responsable activo del colectivo y revisa primero la solicitud.",
        );
      next.worker = action.worker;
      next.coordinator = actor.id;
      next.assignedAt = at;
      next.status = "Asignada";
      next.schedule = undefined;
      title = "Recolector asignado";
      note = worker(action.worker)!.name;
      break;
    case "schedule":
      if (
        !worker(current.worker) ||
        !["Asignada", "Programada"].includes(current.status) ||
        !action.date ||
        !action.time ||
        action.date < dateKey(now)
      )
        throw Error(
          "Confirma el responsable, la fecha futura o de hoy y la hora.",
        );
      next.schedule = {
        date: action.date,
        time: action.time,
        notes: action.notes,
      };
      next.status = "Programada";
      title = "Recolección programada";
      note = action.date + " " + action.time;
      break;
    case "cancel":
      if (!action.notes.trim()) throw Error("Indica el motivo de cancelación.");
      next.status = "Cancelada";
      title = "Solicitud cancelada";
      note = action.notes;
      break;
    case "collect":
    case "correct": {
      const correcting = action.kind === "correct";
      if (
        correcting
          ? actor.role !== "admin" ||
            current.status !== "Recolectada" ||
            !current.collection ||
            !action.notes.trim()
          : current.status !== "Programada" || !current.worker
      )
        throw Error(
          "Confirma la programación o solicita a administración una corrección con motivo.",
        );
      if (
        !action.date ||
        action.date > dateKey(now) ||
        !Number.isFinite(action.weight) ||
        action.weight <= 0 ||
        !action.material.trim() ||
        !action.result.trim()
      )
        throw Error(
          "Completa la fecha real, el material, el resultado y un peso mayor que cero.",
        );
      const rule = state.rules
        .filter(
          (r) =>
            r.group === current.group &&
            r.approved &&
            r.from <= action.date &&
            (!r.until || r.until >= action.date),
        )
        .sort((a, b) => b.from.localeCompare(a.from))[0];
      const rate = current.collection?.rate ?? rule?.rate ?? 0;
      next.collection = {
        date: action.date,
        weight: action.weight,
        material: action.material,
        notes: action.notes,
        result: action.result,
        rate,
      };
      next.status = "Recolectada";
      const credited =
        next.collection.result === "Aprovechable"
          ? next.collection.weight * rate
          : 0;
      const previous =
        current.collection?.result === "Aprovechable"
          ? current.collection.weight * rate
          : 0;
      movements = [
        {
          id: crypto.randomUUID(),
          request: id,
          value: Math.round((credited - previous) * 100) / 100,
          at: correcting ? at : action.date,
          reason: correcting
            ? "Ajuste de recolección"
            : "Recolección confirmada",
        },
        ...movements,
      ];
      title = correcting ? "Recolección corregida" : "Recolección confirmada";
      note =
        (correcting ? current.collection!.weight + " → " : "") +
        action.weight +
        " kg. " +
        action.notes;
      break;
    }
  }
  const event = {
    title,
    at,
    by: state.people.find((p) => p.id === actor.id)?.name ?? actor.role,
    note,
  };
  next.history = [
    ...current.history,
    {
      ...event,
      title:
        action.kind === "correct" || current.status === next.status
          ? title
          : next.status,
    },
  ];
  const notices = [
    { ...event, id: crypto.randomUUID(), request: id, readBy: [actor.id] },
    ...state.notices,
  ];
  if (movements !== state.movements && movements[0].value !== 0)
    notices.unshift({
      ...event,
      title:
        action.kind === "correct" ? "Puntos ajustados" : "Puntos asignados",
      id: crypto.randomUUID(),
      request: id,
      readBy: [actor.id],
    });
  return {
    ...state,
    requests: state.requests.map((r) => (r.id === id ? next : r)),
    movements,
    notices,
    audit: [{ ...event, note: id + " · " + note }, ...state.audit],
  };
}
