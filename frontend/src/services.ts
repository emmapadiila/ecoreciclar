const base = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
type Query = URLSearchParams | undefined;

async function request<T>(
  path: string,
  method = "GET",
  payload?: unknown,
): Promise<T> {
  if (!base)
    throw Error("Configura VITE_API_URL para usar el adaptador FastAPI.");
  const response = await fetch(base + "/api" + path, {
    method,
    credentials: "include",
    headers:
      payload === undefined
        ? undefined
        : { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!response.ok)
    throw Object.assign(Error("FastAPI devolvió un error."), {
      status: response.status,
    });
  return response.status === 204 ? (undefined as T) : response.json();
}
const idPath = (id: string) => "/solicitudes/" + encodeURIComponent(id);
const withQuery = (path: string, params?: Query) =>
  params?.size ? path + "?" + params : path;

export const authService = {
  me: () => request("/usuarios/me"),
  login: (body: unknown) => request("/auth/login", "POST", body),
  logout: () => request("/auth/logout", "POST"),
};
export const usuarioService = {
  list: () => request("/usuarios"),
  me: authService.me,
};
export const solicitudService = {
  create: (body: unknown) => request("/solicitudes", "POST", body),
  list: (params?: Query) => request(withQuery("/solicitudes", params)),
  detail: (id: string) => request(idPath(id)),
  assign: (id: string, body: unknown) =>
    request(idPath(id) + "/asignar", "PATCH", body),
  schedule: (id: string, body: unknown) =>
    request(idPath(id) + "/programar", "PATCH", body),
};
export const coordinadorService = { list: () => request("/coordinadores") };
export const recolectorService = { list: () => request("/recolectores") };
export const recoleccionService = {
  confirm: (id: string, body: unknown) =>
    request(idPath(id) + "/confirmar", "POST", body),
};
export const puntosService = { balance: () => request("/usuarios/me/puntos") };
export const indicadoresService = {
  list: (params?: Query) =>
    request(withQuery("/dashboard/indicadores", params)),
};
export const notificacionService = { list: () => request("/notificaciones") };
