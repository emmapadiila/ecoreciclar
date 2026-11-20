import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { useDemo } from "./store";
import {
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
  groups,
  isCollector,
  isCoordinator,
  normalizePhone,
  number,
  roleGroup,
  roles,
  totalWeight,
  type Article,
  type Group,
  type Person,
  type Request,
  type Role,
  type Rule,
  type State,
} from "./model";

const log = (s: State, title: string, by: string, note: string) => [
  { title, at: new Date().toISOString(), by, note },
  ...s.audit,
];
export function People({
  scope,
  items,
  base,
}: {
  scope: string;
  items: Request[];
  base: string;
}) {
  const { state, actor, save } = useDemo(),
    who = actor!,
    admin = who.role === "admin",
    group = roleGroup(who.role);
  const [edit, setEdit] = useState<Person | "new">(),
    [disable, setDisable] = useState<Person>(),
    [history, setHistory] = useState<Person>();
  const canManage = admin || scope === "recolectores";
  const allowed = (Object.keys(roles) as Role[]).filter((r) =>
    scope === "coordinadores"
      ? isCoordinator(r)
      : scope === "recolectores"
        ? isCollector(r) && (admin || roleGroup(r) === group)
        : scope === "residentes"
          ? r === "hogar" || r === "negocio"
          : true,
  );
  const people = state.people.filter(
    (p) =>
      allowed.includes(p.role) &&
      (scope !== "residentes" || items.some((r) => r.owner === p.id)),
  );
  const title =
    scope === "coordinadores"
      ? "Coordinadores"
      : scope === "residentes"
        ? "Participantes del colectivo"
        : scope === "recolectores"
          ? who.role === "huerta"
            ? "Huerteros"
            : admin
              ? "Recolectores y huerteros"
              : "Recicladores"
          : "Usuarios";
  const subject = edit === "new" ? undefined : edit;
  const name = state.people.find((p) => p.id === who.id)?.name ?? who.role;
  const forPerson = (p: Person) =>
    items.filter(
      (r) => r.worker === p.id || r.owner === p.id || r.coordinator === p.id,
    );
  return (
    <>
      <Heading
        title={title}
        text="Consulta el equipo, los participantes y su historial."
      >
        {canManage && (
          <button className="btn primary" onClick={() => setEdit("new")}>
            <Plus size={17} /> Agregar
          </button>
        )}
      </Heading>
      <Panel>
        {people.length ? (
          <div className="table-wrap">
            <table className="responsive-table">
              <thead>
                <tr>
                  {[
                    "Nombre",
                    "Identificador",
                    "Contacto",
                    "Estado",
                    "Actividad",
                    "Acciones",
                  ].map((x) => (
                    <th key={x}>{x}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {people.map((p) => {
                  const assigned = forPerson(p);
                  const contact =
                    scope === "residentes"
                      ? assigned.find((r) => r.owner === p.id)?.phone
                      : p.phone;
                  return (
                    <tr key={p.id}>
                      <td data-label="Nombre">
                        <strong>{p.name}</strong>
                        <small>
                          {roles[p.role]}{" "}
                          {roleGroup(p.role) && "· " + roleGroup(p.role)}
                        </small>
                      </td>
                      <td data-label="Identificador">{p.id}</td>
                      <td data-label="Contacto">{contact}</td>
                      <td data-label="Estado">
                        {p.active ? "Activo" : "Inactivo"}
                        {admin && p.pilot ? " · Piloto" : ""}
                      </td>
                      <td data-label="Actividad">
                        {assigned.filter((r) => r.worker === p.id).length}{" "}
                        asignadas ·{" "}
                        {assigned.filter((r) => r.collection).length}{" "}
                        completadas · {number(totalWeight(assigned))} kg
                      </td>
                      <td>
                        <div className="actions">
                          <button
                            className="text-link"
                            onClick={() => setHistory(p)}
                          >
                            Historial
                          </button>
                          {canManage && (
                            <>
                              <button
                                className="text-link"
                                onClick={() => setEdit(p)}
                              >
                                Editar
                              </button>
                              {p.active && p.id !== who.id && (
                                <button
                                  className="text-link"
                                  onClick={() => setDisable(p)}
                                >
                                  Desactivar
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No hay registros para este colectivo.</Empty>
        )}
      </Panel>
      {edit && (
        <Dialog
          title={edit === "new" ? "Agregar persona" : "Editar persona"}
          onClose={() => setEdit(undefined)}
        >
          <Form
            onSave={(d) => {
              const role = (
                  subject?.id === who.id ? who.role : value(d, "role")
                ) as Role,
                phone = normalizePhone(value(d, "phone")),
                personName = value(d, "name");
              if (
                !/^3\d{9}$/.test(phone) ||
                !personName ||
                !allowed.includes(role)
              )
                throw Error("Revisa el nombre, el contacto y el perfil.");
              const p: Person = {
                ...subject,
                id: subject?.id ?? crypto.randomUUID(),
                name: personName,
                phone,
                role,
                active: subject?.id === who.id || d.has("active"),
                pilot: admin ? d.has("pilot") : (subject?.pilot ?? false),
              };
              save((s) => {
                if (
                  s.people.some(
                    (x) =>
                      x.id !== p.id && x.phone === p.phone && x.role === p.role,
                  )
                )
                  throw Error("Ya hay una persona con este teléfono y perfil.");
                if (
                  subject &&
                  subject.role !== role &&
                  s.requests.some(
                    (r) =>
                      r.worker === subject.id ||
                      r.owner === subject.id ||
                      r.coordinator === subject.id,
                  )
                )
                  throw Error(
                    "Este perfil tiene actividad vinculada. Crea un perfil nuevo para cambiar de rol.",
                  );
                return {
                  ...s,
                  people: subject
                    ? s.people.map((x) => (x.id === p.id ? p : x))
                    : [...s.people, p],
                  audit: log(
                    s,
                    subject ? "Usuario editado" : "Usuario agregado",
                    name,
                    p.name,
                  ),
                };
              }, "Registro guardado.");
              setEdit(undefined);
            }}
          >
            <Field label="Nombre">
              <input name="name" required defaultValue={subject?.name} />
            </Field>
            <Field label="Contacto autorizado">
              <input
                name="phone"
                required
                type="tel"
                defaultValue={subject?.phone}
              />
            </Field>
            <Field label="Perfil y colectivo">
              <select
                name="role"
                defaultValue={subject?.role ?? allowed[0]}
                disabled={subject?.id === who.id}
              >
                {allowed.map((r) => (
                  <option key={r} value={r}>
                    {roles[r]}
                  </option>
                ))}
              </select>
            </Field>
            <label>
              <input
                name="active"
                type="checkbox"
                defaultChecked={subject?.active ?? true}
                disabled={subject?.id === who.id}
              />{" "}
              Activo
            </label>
            {admin && (
              <label>
                <input
                  name="pilot"
                  type="checkbox"
                  defaultChecked={subject?.pilot ?? false}
                />{" "}
                Habilitado para el piloto
              </label>
            )}
          </Form>
        </Dialog>
      )}
      {disable && (
        <Dialog title="Desactivar perfil" onClose={() => setDisable(undefined)}>
          <p>¿Desactivar el acceso de {disable.name}?</p>
          <Form
            label="Desactivar perfil"
            onSave={() => {
              save(
                (s) => ({
                  ...s,
                  people: s.people.map((p) =>
                    p.id === disable.id ? { ...p, active: false } : p,
                  ),
                  audit: log(s, "Perfil desactivado", name, disable.name),
                }),
                "Perfil desactivado.",
              );
              setDisable(undefined);
            }}
          >
            <p>El historial de recolecciones seguirá disponible.</p>
          </Form>
        </Dialog>
      )}
      {history && (
        <Dialog
          title={"Historial · " + history.name}
          onClose={() => setHistory(undefined)}
        >
          <ul className="activity">
            {forPerson(history).map((r) => (
              <li key={r.id}>
                <Link
                  className="text-link"
                  to={base + "/solicitud/" + r.id}
                  onClick={() => setHistory(undefined)}
                >
                  {r.id}
                </Link>
                <small>{r.status}</small>
              </li>
            ))}
          </ul>
          {!forPerson(history).length && (
            <Empty>No hay actividad registrada.</Empty>
          )}
          {isCollector(history.role) && canManage && (
            <div className="stack">
              <h3>Solicitudes para asignar</h3>
              {items
                .filter(
                  (r) =>
                    roleGroup(history.role) === r.group &&
                    ["En revisión", "Asignada", "Programada"].includes(
                      r.status,
                    ),
                )
                .slice(0, 5)
                .map((r) => (
                  <Link
                    className="text-link"
                    to={base + "/solicitud/" + r.id}
                    key={r.id}
                    onClick={() => setHistory(undefined)}
                  >
                    {r.id} · {r.classification}
                  </Link>
                ))}
            </div>
          )}
        </Dialog>
      )}
    </>
  );
}
export function Rules() {
  const { state, actor, save } = useDemo(),
    [edit, setEdit] = useState<Rule | "new">();
  const rule = edit === "new" ? undefined : edit;
  return (
    <>
      <Heading
        title="Reglas de EcoPuntos"
        text="Ejemplo ficticio: 5 kg × 10 puntos/kg = 50 EcoPuntos. Equivalencias pendientes de validación."
      >
        <button className="btn primary" onClick={() => setEdit("new")}>
          Nueva regla
        </button>
      </Heading>
      <Panel>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Colectivo</th>
                <th>Puntos por kg</th>
                <th>Vigencia</th>
                <th>Aprobación</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {state.rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.group}</td>
                  <td>{number(r.rate)}</td>
                  <td>
                    {dateLabel(r.from)} ·{" "}
                    {r.until ? dateLabel(r.until) : "Sin vencimiento"}
                  </td>
                  <td>{r.approved ? "Aprobada" : "Pendiente"}</td>
                  <td>
                    <button className="text-link" onClick={() => setEdit(r)}>
                      Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel title="Historial de cambios">
        <Timeline
          events={state.audit.filter(
            (e) => e.title === "Regla de EcoPuntos guardada",
          )}
        />
        {!state.audit.some(
          (e) => e.title === "Regla de EcoPuntos guardada",
        ) && <Empty>Aún no se han modificado las reglas.</Empty>}
      </Panel>
      {edit && (
        <Dialog
          title={rule ? "Editar regla" : "Nueva regla"}
          onClose={() => setEdit(undefined)}
        >
          <Form
            onSave={(d) => {
              const next: Rule = {
                id: rule?.id ?? crypto.randomUUID(),
                group: value(d, "group") as Group,
                rate: Number(value(d, "rate")),
                from: value(d, "from"),
                until: value(d, "until"),
                approved: d.has("approved"),
              };
              if (
                !Number.isFinite(next.rate) ||
                next.rate < 0 ||
                !next.from ||
                (next.until && next.until < next.from)
              )
                throw Error("Revisa la tasa y el rango de vigencia.");
              save(
                (s) => ({
                  ...s,
                  rules: [...s.rules.filter((r) => r.id !== next.id), next],
                  audit: log(
                    s,
                    "Regla de EcoPuntos guardada",
                    actor!.id,
                    next.group +
                      " · " +
                      next.rate +
                      " puntos/kg · " +
                      next.from +
                      " · " +
                      (next.until || "Sin vencimiento") +
                      " · " +
                      (next.approved ? "Aprobada" : "Pendiente"),
                  ),
                }),
                "Regla guardada.",
              );
              setEdit(undefined);
            }}
          >
            <Field label="Colectivo">
              <select name="group" defaultValue={rule?.group}>
                {groups.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </Field>
            <Field label="Puntos por kilogramo">
              <input
                name="rate"
                type="number"
                min="0"
                step=".01"
                required
                defaultValue={rule?.rate ?? 10}
              />
            </Field>
            <div className="form-grid">
              <Field label="Vigente desde">
                <input
                  type="date"
                  name="from"
                  required
                  defaultValue={rule?.from ?? dateKey()}
                />
              </Field>
              <Field label="Vigente hasta">
                <input type="date" name="until" defaultValue={rule?.until} />
              </Field>
            </div>
            <label>
              <input
                type="checkbox"
                name="approved"
                defaultChecked={rule?.approved}
              />{" "}
              Regla aprobada
            </label>
          </Form>
        </Dialog>
      )}
    </>
  );
}
export function Content() {
  const { state, actor, save } = useDemo(),
    [edit, setEdit] = useState<Article | "new">();
  const a = edit === "new" ? undefined : edit;
  return (
    <>
      <Heading
        title="Contenidos ambientales"
        text="Las guías publicadas aparecen en la página de educación."
      >
        <button className="btn primary" onClick={() => setEdit("new")}>
          Nueva guía
        </button>
      </Heading>
      <Panel>
        <ul className="activity">
          {state.articles.map((article) => (
            <li key={article.id}>
              <div>
                <strong>{article.title}</strong>
                <small>
                  {article.category} ·{" "}
                  {article.published ? "Publicada" : "Borrador"}
                </small>
              </div>
              <button className="text-link" onClick={() => setEdit(article)}>
                Editar
              </button>
            </li>
          ))}
        </ul>
      </Panel>
      {edit && (
        <Dialog
          title={a ? "Editar guía" : "Nueva guía"}
          onClose={() => setEdit(undefined)}
        >
          <Form
            onSave={(d) => {
              const next = {
                id: a?.id ?? crypto.randomUUID(),
                title: value(d, "title"),
                body: value(d, "body"),
                category: value(d, "category"),
                published: d.has("published"),
              };
              if (!next.title || !next.body)
                throw Error("Completa el título y el contenido.");
              save(
                (s) => ({
                  ...s,
                  articles: a
                    ? s.articles.map((x) => (x.id === a.id ? next : x))
                    : [...s.articles, next],
                  audit: log(s, "Guía guardada", actor!.id, next.title),
                }),
                "Guía guardada.",
              );
              setEdit(undefined);
            }}
          >
            <Field label="Título">
              <input required name="title" defaultValue={a?.title} />
            </Field>
            <Field label="Categoría">
              <select name="category" defaultValue={a?.category}>
                {["Comunidad", ...groups].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </Field>
            <Field label="Contenido">
              <textarea required name="body" defaultValue={a?.body} />
            </Field>
            <label>
              <input
                type="checkbox"
                name="published"
                defaultChecked={a?.published}
              />{" "}
              Publicada
            </label>
          </Form>
        </Dialog>
      )}
    </>
  );
}
export function Audit() {
  const { state } = useDemo();
  return (
    <>
      <Heading
        title="Auditoría"
        text="Actividad operativa y administrativa de la demostración."
      />
      <Panel>
        {state.audit.length ? (
          <Timeline events={state.audit} />
        ) : (
          <Empty>Aún no hay cambios registrados.</Empty>
        )}
      </Panel>
    </>
  );
}
export function Settings() {
  const { state, actor, save, reset } = useDemo(),
    [confirm, setConfirm] = useState(false),
    navigate = useNavigate();
  return (
    <>
      <Heading title="Configuración" />
      <Panel title="Colectivos y parámetros del piloto">
        <Form
          onSave={(d) => {
            const settings = {
              sector: value(d, "sector"),
              recycling: value(d, "recycling"),
              organic: value(d, "organic"),
              pilot: d.has("pilot"),
            };
            if (!settings.sector || !settings.recycling || !settings.organic)
              throw Error("Completa los nombres y el sector.");
            save(
              (s) => ({
                ...s,
                settings,
                audit: log(
                  s,
                  "Configuración editada",
                  actor!.id,
                  settings.sector,
                ),
              }),
              "Configuración actualizada.",
            );
          }}
        >
          <div className="form-grid">
            <Field label="Sector predeterminado">
              <input
                required
                name="sector"
                defaultValue={state.settings.sector}
              />
            </Field>
            <Field label="Colectivo de recicladores">
              <input
                required
                name="recycling"
                defaultValue={state.settings.recycling}
              />
            </Field>
            <Field label="Colectivo de huerteros">
              <input
                required
                name="organic"
                defaultValue={state.settings.organic}
              />
            </Field>
          </div>
          <label>
            <input
              type="checkbox"
              name="pilot"
              defaultChecked={state.settings.pilot}
            />{" "}
            Piloto activo
          </label>
        </Form>
      </Panel>
      <Panel title="Datos de demostración">
        <p>
          Recupera los registros iniciales y borra los cambios de este
          navegador.
        </p>
        <button className="btn secondary" onClick={() => setConfirm(true)}>
          Reiniciar demostración
        </button>
      </Panel>
      {confirm && (
        <Dialog
          title="Reiniciar demostración"
          onClose={() => setConfirm(false)}
        >
          <Form
            label="Reiniciar y salir"
            onSave={() => {
              reset();
              navigate("/acceso");
            }}
          >
            <p>
              Esta acción eliminará las solicitudes y cambios creados en este
              navegador.
            </p>
          </Form>
        </Dialog>
      )}
    </>
  );
}
