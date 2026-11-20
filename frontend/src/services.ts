const base = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/$/, "");
const tokenKey = "ecoconecta360-api-token";
type Query = URLSearchParams | undefined;

export function apiToken() {
  return sessionStorage.getItem(tokenKey);
}

export function clearApiToken() {
  sessionStorage.removeItem(tokenKey);
}

export function setApiToken(token: string) {
  sessionStorage.setItem(tokenKey, token);
}

async function request<T>(
  path: string,
  method = "GET",
  payload?: unknown,
): Promise<T> {
  const token = apiToken();
  const response = await fetch(base + path, {
    method,
    headers: {
      ...(payload === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: "Bearer " + token } : {}),
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw Object.assign(Error(typeof body?.detail === "string" ? body.detail
      : response.status === 422 ? "Revisa los datos del formulario."
      : "No se pudo completar la operación con el servidor."), {
      status: response.status,
    });
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
const idPath = (id: string) => "/solicitudes/" + encodeURIComponent(id);
const withQuery = (path: string, params?: Query) =>
  params?.size ? path + "?" + params : path;

export const authService = {
  me: () => request<{
    id: number;
    nombre: string;
    correo: string;
    rol: "residente" | "coordinador" | "administrador" | "recolector";
    tipo_generador: "hogar" | "negocio";
    colectivo_tipo: "organico" | "reciclable" | null;
  }>("/auth/me"),
  login: async (body: { correo: string; password: string }) => {
    const result = await request<{ access_token: string; token_type: string }>(
      "/auth/token",
      "POST",
      body,
    );
    setApiToken(result.access_token);
    return result;
  },
  logout: () => {
    clearApiToken();
  },
};
export const usuarioService = {
  list: () => request("/usuarios"),
  me: authService.me,
};
export const materialService = {
  list: () => request<Array<{ id: number; nombre: string; categoria: string }>>(
    "/materiales",
  ),
};
export interface ServerRequest {
  id: number;
  codigo: string;
  colectivo_id: number;
  estado: string;
}
export interface ServerRequestDetail extends ServerRequest {
  paso: string;
  residente: string;
  colectivo: string;
  direccion: string;
  descripcion: string | null;
  horario_preferido: string | null;
  fecha_creacion: string;
  materiales: { nombre: string; estimado_kg: number | null }[];
  asignacion: { recolector_id: number; nombre: string; telefono: string | null; fecha: string;
    programada_en: string | null; observaciones: string | null } | null;
  pesaje: { peso_real_kg: string; material: string; regla_id: number | null;
    puntos_por_kg: string | null; puntos: string | null } | null;
  cierre: { peso_real_kg: number; fecha_recoleccion: string; puntos: number } | null;
}
export interface ServerHistory {
  tipo?: string;
  nuevo?: string;
  actor: string;
  fecha: string;
  observacion?: string;
  datos?: Record<string, string | number | null>;
}
export const solicitudService = {
  create: (body: unknown) =>
    request<{ id: number; codigo: string; colectivo_id: number; estado: string }>(
      "/solicitudes",
      "POST",
      body,
    ),
  list: (params?: Query) => request<ServerRequest[]>(withQuery("/solicitudes", params)),
  detail: (id: string) => request<ServerRequestDetail>(idPath(id)),
  history: (id: string) => request<ServerHistory[]>(idPath(id) + "/historial"),
  assign: (id: string, body: unknown) =>
    request(idPath(id) + "/asignacion", "POST", body),
  schedule: (id: string, body: unknown) =>
    request(idPath(id) + "/programacion", "POST", body),
  record: (id: string, action: "estado" | "confirmacion" | "recogida" | "recepcion" | "pesaje", body: unknown) =>
    request(idPath(id) + "/" + action, "POST", body),
};
export const coordinadorService = { list: () => request("/coordinadores") };
export const recolectorService = {
  list: () => request<Array<{ id: number; nombre: string; telefono: string | null; colectivo_id: number }>>("/recolectores"),
};
export const recoleccionService = {
  confirm: (id: string, body: unknown) =>
    request(idPath(id) + "/cierre", "POST", body),
};
export const puntosService = { balance: () => request<{ puntos: string }>("/mi-cuenta/puntos") };
export const indicadoresService = {
  list: (params?: Query) =>
    request(withQuery("/dashboard/indicadores", params)),
  daily: (fecha: string) => request<{
    fecha: string; total_kg: number; reciclables_kg: number; organicos_kg: number;
    recolecciones_confirmadas: number; hogares_participantes: number;
    negocios_participantes: number; ultima_actualizacion: string | null;
  }>(withQuery("/public/resultados-diarios", new URLSearchParams({ fecha }))),
};
export const notificacionService = { list: () => request("/notificaciones") };
