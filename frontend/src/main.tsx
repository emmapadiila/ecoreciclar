import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";
import {
  BarChart3,
  Bell,
  BookOpen,
  CalendarDays,
  ClipboardList,
  Coins,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Scale,
  Settings as SettingsIcon,
  Shield,
  Truck,
  UserRound,
  Users,
} from "lucide-react";
import {
  Access,
  Education,
  IntakePage,
  Landing,
  Lookup,
  PublicLayout,
  Verify,
} from "./public";
import { DemoProvider, useDemo } from "./store";
import { OperationAccess, OperationPanel } from "./request-operation";
import { Brand, Heading } from "./ui";
import { Calendar, Profile, RequestDetail, RequestList } from "./requests";
import { Impact, Notifications, Overview, Points } from "./impact";
import { DailyResults } from "./daily-results";
import { Audit, Content, People, Rules, Settings } from "./admin";
import {
  isCollector,
  isCoordinator,
  isResident,
  roles,
  visibleRequests,
  type Role,
} from "./model";
import "./style.css";

type Item = [string, string, typeof Users];
const summary: Item = ["", "Resumen", LayoutDashboard],
  calendar: Item = ["calendario", "Calendario", CalendarDays],
  profile: Item = ["perfil", "Perfil", UserRound],
  points: Item = ["puntos", "EcoPuntos", Coins],
  reports: Item = ["reportes", "Reportes", BarChart3],
  notifications: Item = ["notificaciones", "Notificaciones", Bell],
  history: Item = ["historial", "Historial", History],
  requests: Item = ["solicitudes", "Solicitudes", ClipboardList],
  collections: Item = ["recolecciones", "Recolecciones", Truck];
function menu(role: Role): Item[] {
  if (role === "admin")
    return [
      ["", "Dashboard", LayoutDashboard],
      ["usuarios", "Usuarios", Users],
      ["coordinadores", "Coordinadores", Shield],
      ["recolectores", "Recolectores", Users],
      requests,
      collections,
      points,
      ["reglas", "Reglas de EcoPuntos", Coins],
      ["contenidos", "Contenidos ambientales", BookOpen],
      ["reportes", "Indicadores", BarChart3],
      ["auditoria", "Auditoría", History],
      ["configuracion", "Configuración", SettingsIcon],
      notifications,
    ];
  if (role === "fundacion")
    return [["", "EcoImpacto", BarChart3], reports, profile];
  if (isResident(role))
    return [
      ["", "Mi resumen", LayoutDashboard],
      ["solicitudes", "Mis solicitudes", ClipboardList],
      ["seguimiento", "Seguimiento", Truck],
      calendar,
      ["historial", "Historial de entregas", History],
      ["reportes", "Mi EcoImpacto", BarChart3],
      points,
      notifications,
      [
        "perfil",
        role === "negocio" ? "Mi establecimiento" : "Mi perfil",
        UserRound,
      ],
    ];
  if (isCollector(role))
    return [["", "Mis asignaciones", Truck], calendar, history, profile];
  return [
    summary,
    role === "huerta"
      ? ["solicitudes", "Solicitudes orgánicas", ClipboardList]
      : requests,
    calendar,
    ["recolectores", role === "huerta" ? "Huerteros" : "Recicladores", Users],
    ["residentes", "Participantes", Users],
    collections,
    ["pesajes", "Pesajes", Scale],
    points,
    history,
    reports,
    notifications,
    profile,
  ];
}
function Problem({ kind = "404" }: { kind?: string }) {
  const problems: Record<string, [string, string]> = {
    "404": ["Página no encontrada", "Comprueba el enlace o vuelve al inicio."],
    permiso: ["Acceso denegado", "Tu perfil no tiene acceso a esta sección."],
    sesion: [
      "Sesión expirada",
      "Elige tu perfil de demostración para continuar.",
    ],
    conexion: [
      "Error de conexión",
      "Comprueba tu conexión y vuelve a intentarlo.",
    ],
  };
  const [title, copy] = problems[kind] ?? problems["404"];
  return (
    <div className="wrap section narrow">
      <Heading title={title} text={copy} />
      <div className="actions">
        <Link className="btn primary" to={kind === "sesion" ? "/acceso" : "/"}>
          {kind === "sesion" ? "Acceder al panel" : "Volver al inicio"}
        </Link>
        {kind === "sesion" && (
          <Link className="btn secondary" to="/verificar">
            Mi EcoConecta
          </Link>
        )}
        {kind === "conexion" && (
          <button
            className="btn secondary"
            onClick={() => window.history.back()}
          >
            Volver a la página anterior
          </button>
        )}
      </div>
    </div>
  );
}
function PanelRoutes() {
  const { state, actor, login } = useDemo(),
    { role, "*": section = "" } = useParams(),
    loc = useLocation(),
    [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(false);
    window.scrollTo(0, 0);
  }, [loc.pathname]);
  if (!role || !Object.hasOwn(roles, role)) return <Problem />;
  if (
    !actor ||
    !state.people.some(
      (p) => p.id === actor.id && p.role === actor.role && p.active,
    )
  )
    return <Navigate to="/sesion-expirada" replace />;
  if (actor.role !== role) return <Navigate to="/acceso-denegado" replace />;
  const base = "/panel/" + role,
    links = menu(actor.role),
    items = visibleRequests(state, actor),
    me = state.people.find((p) => p.id === actor.id)!,
    resident = isResident(actor.role),
    collector = isCollector(actor.role);
  const root = section.split("/")[0];
  const custom =
    (root === "solicitud" && role !== "fundacion") ||
    (root === "asignaciones" && collector);
  if (!links.some(([s]) => s === root) && !custom)
    return <Navigate to="/acceso-denegado" replace />;
  const unread = state.notices.filter(
    (n) =>
      items.some((r) => r.id === n.request) && !n.readBy.includes(actor.id),
  ).length;
  const list = (title: string, filter = items) => (
    <RequestList
      key={title}
      items={filter}
      title={title}
      base={base}
      create={resident && root === "solicitudes"}
    />
  );
  const done = items.filter((r) => r.status === "Recolectada"),
    active = items.filter(
      (r) => r.status !== "Recolectada" && r.status !== "Cancelada",
    );
  return (
    <div className="shell">
      <aside className={"sidebar " + (open ? "open" : "")} id="panel-nav">
        <Brand />
        <div className="side-role">
          <span className="avatar">{me.name.slice(0, 1)}</span>
          <div>
            <strong>{roles[actor.role]}</strong>
            <small>{me.name}</small>
          </div>
        </div>
        <nav aria-label="Navegación del panel">
          {links.map(([s, label, Icon]) => (
            <NavLink key={s} to={base + (s ? "/" + s : "")} end={!s}>
              <Icon size={18} />
              {label}
              {s === "notificaciones" && unread > 0 && (
                <span className="count">{unread}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="side-bottom">
          <Link to={resident ? "/verificar" : "/acceso"}>Cambiar perfil</Link>
          <Link to="/" onClick={() => login(null)}>
            <LogOut size={17} /> Cerrar sesión
          </Link>
        </div>
      </aside>
      <div className="panel-main">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-expanded={open}
            aria-controls="panel-nav"
            aria-label="Menú del panel"
            onClick={() => setOpen(!open)}
          >
            <Menu />
          </button>
          <span>Villas de San Pablo</span>
          <div className="actions">
            <span className="demo-badge">Modo demostración</span>
            {links.some(([s]) => s === "notificaciones") && (
              <Link
                to={base + "/notificaciones"}
                className="icon-button"
                aria-label={"Notificaciones: " + unread + " sin leer"}
              >
                <Bell size={20} />
                {unread > 0 && <sup>{unread}</sup>}
              </Link>
            )}
          </div>
        </header>
        <main id="contenido" className="workspace">
          <Routes>
            <Route
              index
              element={
                role === "fundacion" ? (
                  <Impact items={state.requests} />
                ) : collector ? (
                  list("Mis asignaciones", active)
                ) : (
                  <Overview items={items} base={base} />
                )
              }
            />
            <Route
              path="solicitudes"
              element={list(
                links.find(([s]) => s === "solicitudes")?.[1] ?? "Solicitudes",
              )}
            />
            <Route
              path="solicitud/:id"
              element={<RequestDetail key={section} />}
            />
            <Route
              path="asignaciones"
              element={list("Mis asignaciones", active)}
            />
            <Route path="seguimiento" element={list("Seguimiento", items)} />
            <Route
              path="calendario"
              element={<Calendar items={items} base={base} />}
            />
            <Route
              path="recolecciones"
              element={list(
                "Recolecciones",
                items.filter(
                  (r) =>
                    r.status === "Programada" || r.status === "Recolectada",
                ),
              )}
            />
            <Route
              path="pesajes"
              element={list(
                "Pesajes",
                items.filter(
                  (r) =>
                    r.status === "Programada" || r.status === "Recolectada",
                ),
              )}
            />
            <Route
              path="historial"
              element={list(
                resident ? "Historial de entregas" : "Historial",
                resident || collector
                  ? done
                  : items.filter(
                      (r) =>
                        r.status === "Recolectada" || r.status === "Cancelada",
                    ),
              )}
            />
            <Route
              path="puntos"
              element={<Points items={items} base={base} />}
            />
            <Route
              path="reportes"
              element={
                <Impact items={role === "fundacion" ? state.requests : items} />
              }
            />
            <Route
              path="notificaciones"
              element={<Notifications items={items} base={base} />}
            />
            <Route path="perfil" element={<Profile />} />
            <Route
              path="usuarios"
              element={
                <People
                  key="usuarios"
                  scope="usuarios"
                  items={items}
                  base={base}
                />
              }
            />
            <Route
              path="coordinadores"
              element={
                <People
                  key="coordinadores"
                  scope="coordinadores"
                  items={items}
                  base={base}
                />
              }
            />
            <Route
              path="recolectores"
              element={
                <People
                  key="recolectores"
                  scope="recolectores"
                  items={items}
                  base={base}
                />
              }
            />
            <Route
              path="residentes"
              element={
                <People
                  key="residentes"
                  scope="residentes"
                  items={items}
                  base={base}
                />
              }
            />
            <Route path="contenidos" element={<Content />} />
            <Route path="reglas" element={<Rules />} />
            <Route path="auditoria" element={<Audit />} />
            <Route path="configuracion" element={<Settings />} />
            <Route path="*" element={<Problem />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
function App() {
  return (
    <>
      <a className="skip" href="#contenido">
        Saltar al contenido
      </a>
      <Routes>
        <Route path="/panel/:role/*" element={<PanelRoutes />} />
        <Route element={<PublicLayout />}>
          <Route index element={<Landing />} />
          <Route path="resultados-diarios" element={<DailyResults />} />
          <Route path="educacion" element={<Education />} />
          <Route path="solicitar" element={<IntakePage />} />
          <Route path="consultar" element={<Lookup />} />
          <Route path="acceso" element={<Access />} />
          <Route path="verificar" element={<Verify />} />
          <Route path="acceso-registrado" element={<OperationAccess />} />
          <Route path="operacion" element={<OperationPanel />} />
          <Route path="operacion/solicitud/:id" element={<OperationPanel />} />
          <Route path="acceso-denegado" element={<Problem kind="permiso" />} />
          <Route path="sesion-expirada" element={<Problem kind="sesion" />} />
          <Route path="error-conexion" element={<Problem kind="conexion" />} />
          <Route path="*" element={<Problem />} />
        </Route>
      </Routes>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <DemoProvider>
      <App />
    </DemoProvider>
  </BrowserRouter>,
);
