import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { Check } from "lucide-react";
import { useDemo } from "./store";
import { DailyResults } from "./daily-results";
import { Dialog, Empty, Field, Form, Heading, Panel, value } from "./ui";
import {
  apiToken, authService, puntosService, recoleccionService, recolectorService,
  solicitudService, usuarioService, colectivoService, reglaPuntosService,
  type ServerHistory, type ServerRequest, type ServerRequestDetail,
} from "./services";

const status: Record<string, string> = {
  recibida: "Recibida", en_revision: "En revisión", asignada: "Asignada",
  pendiente: "Pendiente de confirmación", rechazada: "Responsable rechazó",
  confirmada: "Recolector confirmado", programada: "Programada", incidencia: "Incidencia",
  recogida: "Recogida — pendiente de entrega", recibida_material: "Material recibido — pendiente de pesaje",
  pesada: "Pesaje registrado", recolectada: "Recolectada y cerrada", cancelada: "Cancelada",
};
const actions = {
  review: "Revisar solicitud", assign: "Asignar responsable", contact: "Registrar confirmación del recolector",
  schedule: "Programar recolección", pickup: "Registrar resultado de la recogida",
  receipt: "Confirmar recepción del material", weigh: "Registrar pesaje",
  close: "Confirmar recolección y cerrar solicitud", cancel: "Cancelar solicitud",
};
type Action = keyof typeof actions;
const next: Record<string, Action | undefined> = {
  recibida: "review", en_revision: "assign", pendiente: "contact", rechazada: "assign",
  confirmada: "schedule", programada: "pickup", incidencia: "schedule",
  recogida: "receipt", recibida_material: "weigh", pesada: "close",
};
const answers: Record<string, string> = {
  aceptacion: "Sí, aceptó", rechazo: "No, rechazó", sin_respuesta: "No respondió", pendiente: "Pendiente de llamar",
};
const steps = [
  ["recibida", "Solicitud recibida"], ["asignacion", "Recolector asignado"],
  ["confirmacion", "Confirmación telefónica"], ["programacion", "Programación"],
  ["recogida", "Recogida"], ["recepcion", "Entrega del material"],
  ["pesaje", "Pesaje"], ["recolectada", "Cierre y EcoPuntos"],
];
const currentStep: Record<string, number> = {
  recibida: 0, en_revision: 1, pendiente: 2, rechazada: 1, confirmada: 3, programada: 4,
  incidencia: 3, recogida: 5, recibida_material: 6, pesada: 7, recolectada: 8,
};
const formatTime = (date: string) => new Intl.DateTimeFormat("es-CO", {
  dateStyle: "medium", timeStyle: "short", timeZone: "America/Bogota",
}).format(new Date(date));
const bogotaNow = () => new Date(Date.now() - 5 * 3600_000).toISOString().slice(0, 16);
const errorText = (cause: unknown) => cause instanceof Error ? cause.message : "Error de conexión.";
const panelRoles = {
  administrador: "Administración",
  coordinador: "Coordinación",
  residente: "Residente",
};

export function OperationAccess() {
  const navigate = useNavigate();
  const { login } = useDemo();
  const [showPassword, setShowPassword] = useState(false);
  return <div className="wrap section narrow">
    <Heading title="Acceso con cuenta registrada" text="Usa una cuenta autorizada del piloto." />
    <Panel>
      <Form label="Entrar a operación" onSave={async (data) => {
        login(null);
        try {
          await authService.login({ correo: value(data, "correo"), password: String(data.get("password") ?? "") });
          const user = await authService.me();
          if (!Object.hasOwn(panelRoles, user.rol))
            throw Error("Este panel está disponible para administración, coordinación y residentes.");
        } catch (error) {
          authService.logout();
          throw error;
        }
        navigate("/operacion", { replace: true });
      }}>
        <Field label="Correo"><input name="correo" type="email" required autoComplete="username" /></Field>
        <Field label="Contraseña"><input name="password" type={showPassword ? "text" : "password"} required autoComplete="current-password" /></Field>
        <label><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} /> Mostrar contraseña</label>
      </Form>
    </Panel>
    <Link className="text-link mt-4" to="/crear-cuenta">Crear cuenta de residente</Link>
  </div>;
}

export function OperationPanel() {
  const { id } = useParams();
  const navigate = useNavigate();
  const hasSession = Boolean(apiToken());
  const [user, setUser] = useState<Awaited<ReturnType<typeof authService.me>>>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!hasSession) return;
    let active = true;
    authService.me().then((data) => { if (active) setUser(data); }).catch((cause) => {
      if (!active) return;
      if (cause.status === 401) {
        authService.logout();
        navigate("/acceso-registrado", { replace: true });
      } else setError(errorText(cause));
    });
    return () => { active = false; };
  }, [hasSession, navigate]);
  if (!hasSession) return <Navigate to="/acceso-registrado" replace />;
  return <div className="wrap section">
    {error && <p role="alert" className="error">{error}</p>}
    {!user && !error && <p role="status">Validando acceso…</p>}
    {user && <>
      <p className="mb-5"><strong>{user.nombre}</strong> · {Object.hasOwn(panelRoles, user.rol)
        ? panelRoles[user.rol as keyof typeof panelRoles] : "Sin acceso operativo"}</p>
      <div className="actions mb-5">
        <Link className="text-link" to="/operacion">{user.rol === "administrador" ? "Resultados del piloto"
          : user.rol === "coordinador" ? "Solicitudes del colectivo" : "Mis solicitudes"}</Link>
        {user.rol === "residente" && <Link className="text-link" to="/solicitar">Solicitar recolección</Link>}
        <button type="button" className="btn secondary" onClick={() => {
          authService.logout();
          navigate("/acceso-registrado", { replace: true });
        }}>Cerrar sesión</button>
      </div>
      {!Object.hasOwn(panelRoles, user.rol)
        ? <p role="alert">Este perfil no tiene acceso al panel de operación.</p>
        : user.rol === "administrador"
          ? id ? <p role="alert">El perfil administrador supervisa resultados; las solicitudes son gestionadas por el colectivo.</p>
            : <><AdminPointsRules /><AdminUsers /><DailyResults allowDemoFallback={false} /></>
        : id ? <OperationDetail key={id} id={id} manage={user.rol === "coordinador"} />
        : <OperationList resident={user.rol === "residente"} />}
    </>}
  </div>;
}

function AdminPointsRules() {
  const [groups, setGroups] = useState<Awaited<ReturnType<typeof colectivoService.list>>>([]);
  const [rules, setRules] = useState<Awaited<ReturnType<typeof reglaPuntosService.list>>>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([colectivoService.list(), reglaPuntosService.list()]).then(([collectives, tariffs]) => {
      if (active) { setGroups(collectives); setRules(tariffs); setError(""); }
    }).catch((cause) => { if (active) setError(errorText(cause)); });
    return () => { active = false; };
  }, [refresh]);
  async function publish(data: FormData) {
    const start = value(data, "fecha_inicio");
    await reglaPuntosService.publish({
      colectivo_id: Number(value(data, "colectivo_id")),
      puntos_por_kg: value(data, "puntos_por_kg"),
      fecha_inicio: start ? new Date(start).toISOString() : undefined,
    });
    setEditing(false);
    setRefresh((count) => count + 1);
  }
  const date = (iso: string) => new Date(iso).toLocaleString("es-CO");
  return <>
    <Heading title="Reglas de EcoPuntos" />
    <Panel>
      <button type="button" className="btn primary" disabled={!groups.length} onClick={() => setEditing(true)}>Publicar tarifa</button>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="table-wrap"><table><thead><tr><th>Colectivo</th><th>EcoPuntos por kg</th><th>Desde</th><th>Hasta</th></tr></thead>
        <tbody>{rules.map((rule) => <tr key={rule.id}>
          <td>{groups.find((group) => group.id === rule.colectivo_id)?.nombre ?? rule.colectivo_id}</td>
          <td>{Number(rule.puntos_por_kg).toLocaleString("es-CO")}</td><td>{date(rule.fecha_inicio)}</td>
          <td>{rule.fecha_fin ? date(rule.fecha_fin) : "Sin fecha de fin"}</td>
        </tr>)}</tbody>
      </table></div>
    </Panel>
    {editing && <Dialog title="Publicar tarifa de EcoPuntos" onClose={() => setEditing(false)}>
      <Form label="Publicar tarifa" onSave={publish}>
        <Field label="Colectivo"><select name="colectivo_id" required>{groups.map((group) => <option key={group.id} value={group.id}>{group.nombre}</option>)}</select></Field>
        <Field label="EcoPuntos por kilo"><input name="puntos_por_kg" type="number" min="0" max="100" step="0.01" required /></Field>
        <Field label="Vigencia desde (hora local)"><input name="fecha_inicio" type="datetime-local" /></Field>
        <p>Deja la fecha vacía para aplicar la tarifa desde ahora.</p>
      </Form>
    </Dialog>}
  </>;
}

function AdminUsers() {
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [collectives, setCollectives] = useState<Array<{ id: number; nombre: string }>>([]);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number>();
  useEffect(() => {
    let active = true;
    let timer: number;
    setError("");
    async function load() {
      try {
        const [people, groups] = await Promise.all([usuarioService.list(), colectivoService.list()]);
        if (!active) return;
        setUsers(people as Array<Record<string, unknown>>);
        setCollectives(groups);
      } catch (cause) {
        if (active) setError(errorText(cause));
      } finally {
        if (active) {
          setLoading(false);
          timer = window.setTimeout(load, 10_000);
        }
      }
    }
    void load();
    return () => { active = false; window.clearTimeout(timer); };
  }, [refresh]);
  async function create(data: FormData) {
    const password = String(data.get("password") ?? "");
    await usuarioService.create({
      nombre: value(data, "nombre"),
      correo: value(data, "correo"),
      password,
      confirm_password: password,
      telefono: value(data, "telefono") || undefined,
      direccion: value(data, "direccion") || undefined,
      tipo_generador: value(data, "tipo_generador"),
      rol: value(data, "rol"),
      activo: data.has("activo"),
      piloto_habilitado: data.has("piloto_habilitado"),
      colectivo_id: value(data, "colectivo_id") ? Number(value(data, "colectivo_id")) : undefined,
    });
    setCreateOpen(false);
    setRefresh((count) => count + 1);
  }
  async function toggleActive(id: number, enabled: boolean) {
    setBusy(id);
    try {
      await usuarioService.update(id, { activo: enabled });
      setRefresh((count) => count + 1);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(undefined); }
  }
  async function removeUser(id: number, name: string) {
    if (!window.confirm(`¿Borrar a ${name}? Se borran los datos de su cuenta y el contenido de sus mensajes. Su correo o WhatsApp `
      + "queda libre para un registro nuevo. Se conservan las solicitudes y sus puntos en el historial. No se puede deshacer.")) return;
    setBusy(id);
    try {
      await usuarioService.remove(id);
      setRefresh((count) => count + 1);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(undefined); }
  }
  return <>
    <Heading title="Usuarios registrados" text="Administración de residentes, coordinadores y cuentas administrativas." />
    <div className="actions mb-5"><button type="button" className="btn primary" onClick={() => setCreateOpen(true)}>Crear usuario</button></div>
    {error && <p role="alert" className="error">{error}</p>}
    <Panel>
      {loading ? <p role="status">Cargando usuarios…</p> : !users.length ? <p>No hay usuarios para mostrar.</p> :
        <div className="table-wrap"><table><thead><tr><th>Nombre</th><th>Correo</th><th>WhatsApp</th><th>Rol</th><th>Estado</th><th>Piloto</th><th>Acciones</th></tr></thead>
          <tbody>{users.map((person) => <tr key={String(person.id)}>
            <td>{String(person.nombre)}</td><td>{String(person.correo ?? "—")}</td><td>{String(person.whatsapp_id ?? "—")}</td><td>{String(person.rol)}</td>
            <td>{person.activo ? "Activo" : "Inactivo"}</td>
            <td>{person.piloto_habilitado ? "Habilitado" : "Pendiente"}</td>
            <td><div className="actions">
              <button type="button" className="text-link" disabled={busy !== undefined} onClick={() => toggleActive(Number(person.id), !Boolean(person.activo))}>
                {person.activo ? "Desactivar" : "Activar"}</button>
              {person.rol !== "administrador" && <button type="button" className="text-link" disabled={busy !== undefined} onClick={() => removeUser(Number(person.id), String(person.nombre))}>
                Borrar</button>}
            </div></td>
          </tr>)}</tbody></table></div>}
    </Panel>
    {createOpen && <Dialog title="Crear usuario" onClose={() => setCreateOpen(false)}>
      <Form label="Crear usuario" onSave={create}>
        <Field label="Nombre completo"><input name="nombre" required minLength={2} maxLength={120} /></Field>
        <Field label="Correo"><input name="correo" type="email" required /></Field>
        <Field label="Contraseña inicial"><input name="password" type="password" required minLength={12} /></Field>
        <Field label="Teléfono"><input name="telefono" maxLength={20} /></Field>
        <Field label="Dirección"><input name="direccion" maxLength={1000} /></Field>
        <Field label="Tipo de generador">
          <select name="tipo_generador" defaultValue="hogar"><option value="hogar">Hogar</option><option value="negocio">Negocio</option></select>
        </Field>
        <Field label="Rol">
          <select name="rol" defaultValue="residente"><option value="residente">Residente</option><option value="coordinador">Coordinador</option></select>
        </Field>
        <Field label="Colectivo"><select name="colectivo_id" defaultValue=""><option value="">Sin colectivo</option>{collectives.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}</select></Field>
        <label><input type="checkbox" name="activo" defaultChecked /> Activo</label>
        <label><input type="checkbox" name="piloto_habilitado" /> Habilitado para el piloto</label>
      </Form>
    </Dialog>}
  </>;
}

function OperationList({ resident }: { resident: boolean }) {
  const [items, setItems] = useState<ServerRequest[]>();
  const [balance, setBalance] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setItems(undefined);
    setError("");
    Promise.all([
      solicitudService.list(new URLSearchParams({ offset: String(offset) })),
      resident ? puntosService.balance() : null,
    ]).then(([requests, points]) => {
      if (active) { setItems(requests); setBalance(points?.puntos ?? ""); }
    }).catch((cause) => { if (active) setError(errorText(cause)); });
    return () => { active = false; };
  }, [offset, resident]);
  return <>
    <Heading title={resident ? "Mis solicitudes" : "Solicitudes del colectivo"}
      text={resident && balance !== "" ? `Saldo de EcoPuntos: ${balance}` : undefined} />
    <Panel>
      {error ? <p role="alert" className="error">{error}</p>
        : !items ? <p role="status">Cargando solicitudes…</p>
        : !items.length ? <Empty>No hay solicitudes en esta página.</Empty>
        : <ul className="stack">{items.map((item) =>
          <li className="line" key={item.id}><Link className="text-link" to={`/operacion/solicitud/${item.id}`}>{item.codigo}</Link>
            <span>{status[item.estado]}</span></li>)}</ul>}
      <div className="actions">
        {offset > 0 && <button type="button" className="btn secondary" onClick={() => setOffset(offset - 100)}>Anterior</button>}
        {items?.length === 100 && <button type="button" className="btn secondary" onClick={() => setOffset(offset + 100)}>Siguiente</button>}
      </div>
    </Panel>
  </>;
}

function OperationDetail({ id, manage }: { id: string; manage: boolean }) {
  const [detail, setDetail] = useState<ServerRequestDetail>();
  const [history, setHistory] = useState<ServerHistory[]>([]);
  const [workers, setWorkers] = useState<Awaited<ReturnType<typeof recolectorService.list>>>([]);
  const [action, setAction] = useState<Action>();
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(Date.now);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([solicitudService.detail(id), solicitudService.history(id), manage ? recolectorService.list() : []])
      .then(([item, events, collectors]) => {
        if (!active) return;
        setDetail(item);
        setHistory(events);
        setWorkers(collectors.filter((worker) => worker.colectivo_id === item.colectivo_id));
      }).catch((cause) => { if (active) setError(errorText(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, manage, refresh]);
  const scheduled = detail?.asignacion?.programada_en;
  const scheduledTime = scheduled ? Date.parse(scheduled) : 0;
  useEffect(() => {
    if (detail?.paso !== "programada" || !manage) return;
    const wait = scheduledTime - Date.now();
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setClock(Date.now()), Math.min(wait + 100, 2_147_483_000));
    return () => window.clearTimeout(timer);
  }, [clock, scheduledTime, detail?.paso, manage]);
  if (error) return <Panel><p role="alert" className="error">{error}</p>
    <button className="btn secondary" onClick={() => setRefresh(refresh + 1)}>Reintentar</button></Panel>;
  if (!detail) return <p role="status">Cargando solicitud…</p>;
  const item = detail;
  const worker = item.asignacion;
  const primary = next[item.paso];
  const start = history.map((event) => event.tipo).lastIndexOf("asignacion");
  const recent = history.slice(Math.max(0, start)).reverse();
  const lastContact = recent.find((event) => event.tipo === "confirmacion");
  const canReassign = lastContact?.datos?.respuesta === "sin_respuesta" && item.paso === "pendiente";
  const materials = item.materiales.map((material) => material.nombre).join(", ");
  const pickup = recent.find((event) => event.tipo === "recogida");
  const receipt = recent.find((event) => event.tipo === "recepcion");
  const pickupEarly = scheduledTime > Math.max(clock, Date.now());
  const facts = [
    ["Solicitante", item.residente], ["Colectivo", item.colectivo], ["Dirección", item.direccion],
    ["Materiales", materials], ["Descripción", item.descripcion], ["Horario preferido", item.horario_preferido],
  ];

  async function submit(data: FormData) {
    const observaciones = value(data, "notes");
    const timestamp = value(data, "when") + ":00-05:00";
    switch (action) {
      case "review": await solicitudService.record(id, "estado", { estado: "en_revision", observacion: "Revisión por coordinación", confirmar_materiales: true }); break;
      case "cancel": await solicitudService.record(id, "estado", { estado: "cancelada", observacion: observaciones }); break;
      case "assign": await solicitudService.assign(id, { recolector_id: Number(value(data, "worker")) }); break;
      case "contact": await solicitudService.record(id, "confirmacion", { respuesta: value(data, "answer"), recolector_id: worker?.recolector_id, observaciones }); break;
      case "schedule": await solicitudService.schedule(id, { programada_en: timestamp, observaciones }); break;
      case "pickup": await solicitudService.record(id, "recogida", { fecha_real: timestamp, resultado: value(data, "result"), observaciones }); break;
      case "receipt": await solicitudService.record(id, "recepcion", { fecha_real: timestamp, material: value(data, "material"), observaciones }); break;
      case "weigh": await solicitudService.record(id, "pesaje", { peso_real_kg: value(data, "weight"), material: value(data, "material"), observaciones }); break;
      case "close": await recoleccionService.confirm(id, { regla_id: item.pesaje?.regla_id, puntos_previstos: item.pesaje?.puntos }); break;
    }
    setAction(undefined);
    setLoading(true);
    setRefresh((count) => count + 1);
  }
  return <>
    <Heading title={item.codigo} text={status[item.paso]} />
    {manage && primary && <div className="actions mb-5">
      <button type="button" className="btn primary" onClick={() => setAction(primary)}
        disabled={loading || (primary === "pickup" && Boolean(pickupEarly)) || (primary === "close" && !item.pesaje?.regla_id)}>
        {actions[primary]}</button>
      {(canReassign || item.paso === "rechazada") && <button type="button" className="btn secondary" onClick={() => setAction(item.paso === "rechazada" ? "contact" : "assign")}>
        {item.paso === "rechazada" ? "Registrar otro intento" : "Asignar otra persona"}</button>}
      {primary === "close" && <button type="button" className="btn secondary" disabled={loading}
        onClick={() => setRefresh(refresh + 1)}>Consultar regla vigente</button>}
      <button type="button" className="btn secondary" disabled={loading} onClick={() => setAction("cancel")}>{actions.cancel}</button>
    </div>}
    {primary === "pickup" && pickupEarly && <p className="hint">Podrás registrar la recogida desde la hora programada.</p>}
    <div className="detail-grid">
      <div className="stack">
        <Panel title="Datos de la solicitud"><dl className="facts">{facts.map(([label, entry]) =>
          <div key={label}><dt>{label}</dt><dd>{entry || "—"}</dd></div>)}</dl></Panel>
        {worker && <Panel title="Responsable asignado">
          <p><strong>{worker.nombre}</strong> · {item.colectivo}</p>
          {worker.telefono && <p><a className="text-link" href={"tel:" + worker.telefono}>{worker.telefono}</a></p>}
          <p>Asignación: {formatTime(worker.fecha)}</p>
          {manage && <p>Confirmación telefónica: {answers[String(lastContact?.datos?.respuesta)] ?? "Pendiente"}</p>}
          {worker.programada_en && <p>Programada: {formatTime(worker.programada_en)} {worker.observaciones && "· " + worker.observaciones}</p>}
        </Panel>}
        {item.pesaje && <Panel title="Pesaje registrado">
          <p>Peso confirmado: <strong>{item.pesaje.peso_real_kg} kg</strong> · {item.pesaje.material}</p>
          <p>{item.pesaje.regla_id
            ? `EcoPuntos estimados: ${item.pesaje.puntos} con la regla de ${item.pesaje.puntos_por_kg} puntos/kg.`
            : "Hace falta una regla de EcoPuntos aprobada y vigente para cerrar."}</p>
        </Panel>}
        {item.cierre && <Panel title="Recolección cerrada">
          <p>{item.cierre.peso_real_kg} kg · {item.cierre.puntos} EcoPuntos acreditados</p>
          <p>{formatTime(item.cierre.fecha_recoleccion)}</p>
        </Panel>}
      </div>
      <div className="stack">
        <Panel title="Seguimiento"><ol className="timeline">{steps.map(([kind, label], index) => {
          const event = (index === 0 || index === 7 ? history.slice().reverse() : recent).find((entry) =>
            (entry.tipo ?? entry.nuevo) === kind && (kind !== "confirmacion" || !manage || entry.datos?.respuesta === "aceptacion"));
          const step = currentStep[item.paso];
          return <li key={kind} className={!event && step !== index ? "future" : undefined}
            aria-current={step === index ? "step" : undefined}>
            <span>{event && <Check size={14} />}</span>
            <div><strong>{label}</strong><small>{event ? `${formatTime(event.fecha)} · ${event.actor}` : "Pendiente"}
              {step === index && " · Siguiente paso"}</small></div>
          </li>;
        })}</ol></Panel>
        <Panel title="Historial"><ol className="timeline">{history.map((event, index) => {
          const kind = event.tipo ?? event.nuevo ?? "";
          const label = steps.find(([key]) => key === kind)?.[1] ?? status[kind] ?? kind;
          return <li key={index}><span><Check size={14} /></span><div><strong>{label}</strong><small>{formatTime(event.fecha)} · {event.actor}</small>
            {event.datos?.respuesta && <p>{answers[String(event.datos.respuesta)]}</p>}
            {event.datos?.anterior_id && <p>Reasignación: responsable anterior #{event.datos.anterior_id}</p>}
            {event.datos?.fecha_real && <p>{formatTime(String(event.datos.fecha_real))}</p>}
            {event.datos?.material && <p>{event.datos.material}</p>}
            {(event.observacion || event.datos?.observaciones) && <p>{event.observacion || event.datos?.observaciones}</p>}
          </div></li>;
        })}</ol></Panel>
      </div>
    </div>
    {action && <Dialog title={actions[action]} onClose={() => setAction(undefined)}>
      <Form label={action === "contact" ? "Guardar respuesta" : "Confirmar"} onSave={submit}>
        {action === "review" && <p>Confirma que revisaste la solicitud y los materiales indicados: {materials}.</p>}
        {action === "assign" && <Field label="Responsable del colectivo"><select name="worker" required defaultValue="">
          <option value="">Selecciona un recolector</option>
          {workers.filter((person) => person.id !== worker?.recolector_id).map((person) =>
            <option key={person.id} value={person.id}>{person.nombre}</option>)}
        </select></Field>}
        {action === "contact" && <Field label="¿El recolector confirmó por teléfono que realizará la recogida?">
          <select name="answer" required defaultValue=""><option value="">Selecciona una respuesta</option>
            {Object.entries(answers).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select></Field>}
        {action === "schedule" && <p>{worker?.nombre} · {item.direccion}. Se dejará un aviso de WhatsApp pendiente.</p>}
        {(action === "pickup" || action === "receipt" || action === "schedule") &&
          <Field label={action === "schedule" ? "Fecha y hora programadas (Barranquilla)" : "Fecha y hora reales (Barranquilla)"}>
            <input name="when" type="datetime-local" required min={action === "schedule" ? bogotaNow() : undefined}
              max={action !== "schedule" ? bogotaNow() : undefined} defaultValue={action !== "schedule" ? bogotaNow() : undefined} />
          </Field>}
        {action === "pickup" && <Field label="Resultado del servicio"><select name="result" required>
          <option value="realizada">Recogida realizada</option><option value="incidencia">No se realizó · registrar incidencia</option>
        </select></Field>}
        {action === "receipt" && <p>Entrega a cargo de {worker?.nombre}.</p>}
        {action === "weigh" && <>
          <p>{item.codigo} · {item.residente} · {worker?.nombre}</p>
          <p>Recogida: {pickup?.datos?.fecha_real && formatTime(String(pickup.datos.fecha_real))} · Recepción: {receipt?.datos?.fecha_real && formatTime(String(receipt.datos.fecha_real))}</p>
          <p>Estimados: {item.materiales.map((material) => material.estimado_kg ? `${material.nombre}: ${material.estimado_kg} kg` : material.nombre).join(", ")}</p>
          <Field label="Peso real (kg)"><input name="weight" type="number" min=".01" max="99999999.99" step=".01" required /></Field>
        </>}
        {(action === "weigh" || action === "receipt") && <Field label={action === "weigh" ? "Material confirmado" : "Material entregado"}>
          <input name="material" maxLength={200} defaultValue={(String(receipt?.datos?.material ?? materials)).slice(0, 200)} required /></Field>}
        {action === "close" && item.pesaje && <p>{item.codigo} · {item.residente} · {item.colectivo} · {worker?.nombre}<br />
          Peso real: {item.pesaje.peso_real_kg} kg · Regla #{item.pesaje.regla_id}: {item.pesaje.puntos_por_kg} puntos/kg<br />
          EcoPuntos que se acreditarán: <strong>{item.pesaje.puntos}</strong>.</p>}
        {(["contact", "schedule", "pickup", "receipt", "weigh", "cancel"] as Action[]).includes(action) &&
          <Field label={action === "cancel" ? "Motivo de cancelación" : "Observaciones"}>
            <textarea name="notes" maxLength={1000} required={action === "cancel"} /></Field>}
      </Form>
    </Dialog>}
  </>;
}
