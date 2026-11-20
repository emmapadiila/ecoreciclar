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
export const solicitudService = {
  create: (body: unknown) =>
    request<{ id: number; codigo: string; colectivo_id: number; estado: string }>(
      "/solicitudes",
      "POST",
      body,
    ),
  list: (params?: Query) => request(withQuery("/solicitudes", params)),
  detail: (id: string) => request(idPath(id)),
  assign: (id: string, body: unknown) =>
    request(idPath(id) + "/asignar", "PATCH", body),
  schedule: (id: string, body: unknown) =>
    request(idPath(id) + "/programar", "PATCH", body),
};
export const coordinadorService = { list: () => request("/coordinadores") };
export const recolectorService = {
  list: () => request<Array<{ id: number; nombre: string; telefono: string | null; colectivo_id: number }>>("/recolectores"),
};
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
