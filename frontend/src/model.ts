export const groups = ["Reciclable", "Orgánico"] as const;
export type Group = (typeof groups)[number];
export const statuses = [
  "Recibida",
  "En revisión",
  "Asignada",
  "Programada",
  "Recolectada",
  "Cancelada",
] as const;
export type Status = (typeof statuses)[number];
export type Role =
  | "reciclaje"
  | "huerta"
  | "reciclador"
  | "huertero"
  | "admin"
  | "fundacion"
  | "hogar"
  | "negocio";
export const roles: Record<Role, string> = {
  reciclaje: "Coordinación de reciclaje",
  huerta: "Coordinación de huerta",
  reciclador: "Recolector de reciclaje",
  huertero: "Huertero",
  admin: "Administración",
  fundacion: "Visor de Fundación",
  hogar: "Hogar",
  negocio: "Unidad productiva",
};
export const roleGroup = (role: Role) =>
  role === "reciclaje" || role === "reciclador"
    ? groups[0]
    : role === "huerta" || role === "huertero"
      ? groups[1]
      : undefined;
export const isCoordinator = (role: Role) =>
  role === "reciclaje" || role === "huerta";
export const isCollector = (role: Role) =>
  role === "reciclador" || role === "huertero";
export const isResident = (role: Role) =>
  role === "hogar" || role === "negocio";
export interface Actor {
  role: Role;
  id: string;
}
export interface Person {
  id: string;
  name: string;
  phone: string;
  role: Role;
  active: boolean;
  pilot: boolean;
  address?: string;
  availability?: string;
}
export interface Intake {
  name: string;
  phone: string;
  generator: "hogar" | "negocio";
  sector: string;
  address: string;
  references: string;
  group: Group;
  classification: string;
  description: string;
  photo?: string;
  estimate?: number;
  preferred: string;
  notes: string;
  ai?: string;
}
export interface Event {
  title: string;
  at: string;
  by: string;
  note?: string;
}
export interface Request extends Intake {
  id: string;
  owner: string;
  created: string;
  status: Status;
  history: Event[];
  worker?: string;
  coordinator?: string;
  assignedAt?: string;
  schedule?: { date: string; time: string; notes: string };
  collection?: {
    date: string;
    weight: number;
    material: string;
    notes: string;
    result: string;
    rate: number;
  };
}
export interface Rule {
  id: string;
  group: Group;
  rate: number;
  from: string;
  until: string;
  approved: boolean;
}
export interface Movement {
  id: string;
  request: string;
  value: number;
  at: string;
  reason: string;
}
export interface Notice extends Event {
  id: string;
  request: string;
  readBy: string[];
}
export interface Article {
  id: string;
  title: string;
  body: string;
  category: string;
  published: boolean;
}
export interface State {
  people: Person[];
  requests: Request[];
  rules: Rule[];
  movements: Movement[];
  notices: Notice[];
  audit: Event[];
  articles: Article[];
  settings: {
    sector: string;
    pilot: boolean;
    recycling: string;
    organic: string;
  };
}
export const dateKey = (date = new Date()) =>
  [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
export const dateLabel = (date?: string) =>
  date
    ? new Intl.DateTimeFormat("es-CO", { dateStyle: "medium" }).format(
        new Date(date.length === 10 ? date + "T12:00:00" : date),
      )
    : "—";
export const number = (value: number) =>
  new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(value);
export const normalizePhone = (value: string) =>
  value.replace(/\D/g, "").replace(/^57(?=\d{10}$)/, "");
export function visibleRequests(state: State, actor: Actor) {
  if (actor.role === "admin") return state.requests;
  if (actor.role === "fundacion") return [];
  if (isResident(actor.role))
    return state.requests.filter((r) => r.owner === actor.id);
  return state.requests.filter(
    (r) =>
      r.group === roleGroup(actor.role) &&
      (!isCollector(actor.role) || r.worker === actor.id),
  );
}
export const totalWeight = (items: Request[]) =>
  items.reduce((sum, item) => sum + (item.collection?.weight ?? 0), 0);
export const totalPoints = (state: State, items: Request[]) => {
  const ids = new Set(items.map((item) => item.id));
  return state.movements.reduce(
    (sum, movement) => sum + (ids.has(movement.request) ? movement.value : 0),
    0,
  );
};
