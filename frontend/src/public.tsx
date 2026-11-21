import { useEffect, useState } from "react";
import {
  Link,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  BookOpen,
  CalendarCheck,
  Camera,
  ClipboardList,
  Coins,
  Leaf,
  MapPin,
  Menu,
  MessageCircle,
  Recycle,
  Search,
  ShieldCheck,
  Sprout,
  Trash2,
  Users,
} from "lucide-react";
import {
  Badge,
  Brand,
  Empty,
  Field,
  Form,
  Heading,
  imageData,
  Panel,
  value,
} from "./ui";
import {
  dateLabel,
  isResident,
  normalizePhone,
  number,
  roles,
  totalPoints,
  totalWeight,
  type Group,
  type Intake,
  type Role,
} from "./model";
import { useDemo } from "./store";
import { createRequest } from "./operations";
import {
  apiToken,
  authService,
  clearApiToken,
  materialService,
  solicitudService,
} from "./services";

const nav = [
  ["Inicio", "/"],
  ["Educación ambiental", "/educacion"],
  ["Resultados diarios", "/resultados-diarios"],
  ["Consultar solicitud", "/consultar"],
];
const whatsappNumber = (import.meta.env.VITE_WHATSAPP_NUMBER ?? "").trim();
const whatsappUrl = /^[1-9]\d{7,14}$/.test(whatsappNumber)
  ? `https://wa.me/${whatsappNumber}?text=${encodeURIComponent("Hola, EcoConecta. Quiero solicitar una recolección de residuos.")}`
  : null;
function WhatsAppLink({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return whatsappUrl ? <a className="btn primary" href={whatsappUrl} target="_blank" rel="noopener noreferrer" onClick={onClick}>{children}</a>
    : <span className="whatsapp-pending"><button className="btn primary" type="button" disabled>{children}</button><small>WhatsApp pendiente de configuración</small></span>;
}
export function PublicLayout() {
  const [open, setOpen] = useState(false),
    location = useLocation();
  useEffect(() => {
    if (location.hash)
      requestAnimationFrame(() =>
        document.getElementById(location.hash.slice(1))?.scrollIntoView(),
      );
    else window.scrollTo(0, 0);
  }, [location]);
  return (
    <>
      <header className="public-header">
        <div className="wrap topnav">
          <Brand />
          <button
            className="icon-button mobile-menu"
            aria-label={open ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={open}
            aria-controls="public-nav"
            onClick={() => setOpen(!open)}
          >
            <Menu />
          </button>
          <nav
            id="public-nav"
            className={open ? "open" : ""}
            aria-label="Navegación pública"
          >
            {nav.map(([label, to]) => (
              <Link key={to} to={to} onClick={() => setOpen(false)}>
                {label}
              </Link>
            ))}
            <WhatsAppLink onClick={() => setOpen(false)}><MessageCircle size={17} /> Solicitar por WhatsApp</WhatsAppLink>
          </nav>
        </div>
      </header>
      <main id="contenido">
        <Outlet />
      </main>
      <footer>
        <div className="wrap footer-grid">
          <div>
            <Brand />
            <p>Conectamos residuos con nuevas oportunidades.</p>
            <small>Villas de San Pablo · Barranquilla, Colombia</small>
          </div>
          <div>
            <strong>Comunidad</strong>
            <Link to="/educacion">Educación ambiental</Link>
            <Link to="/verificar">Mi EcoConecta</Link>
            <WhatsAppLink>Solicitar por WhatsApp</WhatsAppLink>
          </div>
          <div>
            <strong>Operación</strong>
            <Link to="/acceso">Acceso al panel</Link>
            <Link to="/consultar">Consultar solicitud</Link>
            <small>Universidad Libre · Fundación Santo Domingo</small>
          </div>
        </div>
      </footer>
    </>
  );
}
const steps = [
  [MessageCircle, "Escribe por WhatsApp", "Contacta a EcoConecta para comenzar."],
  [Camera, "Comparte tus residuos", "Envía una fotografía o describe los materiales."],
  [Sprout, "Recibe orientación", "La IA te orientará sobre tus residuos."],
  [ClipboardList, "Confirma tu solicitud", "Comparte los datos necesarios para la recolección."],
  [CalendarCheck, "Espera la programación", "El coordinador organizará la recolección."],
  [Coins, "Entrega y suma EcoPuntos", "Los puntos se acreditan cuando se confirma el pesaje."],
] as const;
const categories = [
  [Sprout, "Orgánico", "Cáscaras y restos vegetales aptos para huerta."],
  [Recycle, "Reciclable", "Cartón, papel y envases limpios y secos."],
  [
    Trash2,
    "No aprovechable",
    "Consulta cómo disponer del material con tu prestador de aseo.",
  ],
] as const;
export function Landing() {
  return (
    <>
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <div className="location">
              <MapPin size={15} /> Villas de San Pablo, Barranquilla
            </div>
            <h1>
              Tus residuos pueden <em>transformar tu comunidad.</em>
            </h1>
            <p>
              Identifica tus residuos, solicita su recolección desde WhatsApp y
              contribuye a construir una Villas de San Pablo más sostenible.
            </p>
            <div className="actions">
              <WhatsAppLink>
                <MessageCircle size={19} /> Solicitar recolección
              </WhatsAppLink>
              <Link className="btn secondary" to="/#como-funciona">
                Cómo funciona <ArrowDown size={16} />
              </Link>
            </div>
            <div className="hero-note">
              <ShieldCheck size={16} /> Plataforma registrada del proyecto piloto
            </div>
          </div>
          <figure className="hero-art">
            <img
              src="/comunidad.webp"
              alt="Vecinos separando materiales y cuidando una huerta comunitaria"
            />
            <figcaption>
              <Sprout size={24} />
              <span>
                <strong>El cambio empieza en el barrio</strong>
                <small>Economía circular en Villas de San Pablo</small>
              </span>
            </figcaption>
          </figure>
        </div>
      </section>
      <div className="partners">
        <div className="wrap">
          <span>Una iniciativa para Villas de San Pablo</span>
          <strong>Universidad Libre</strong>
          <img
            src="/identidad/fundacion-santo-domingo.png"
            alt="Fundación Santo Domingo"
          />
          <img
            src="/identidad/villas-san-pablo.png"
            alt="Villas de San Pablo"
          />
        </div>
      </div>
      <section className="wrap section" id="como-funciona">
        <div className="section-heading">
          <h2>Cómo funciona</h2>
          <p>De separar en casa a entregar al colectivo de tu comunidad.</p>
        </div>
        <div className="step-grid">
          {steps.map(([Icon, title, copy], i) => (
            <div key={title}>
              <span className="step-icon">
                <Icon size={23} />
              </span>
              <small>Paso {i + 1}</small>
              <h3>{title}</h3>
              <p>{copy}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="wrap section split">
        <div>
          <Users />
          <h2>Separar en casa beneficia a todo el barrio</h2>
          <p>
            Los reciclables vuelven a circular y los restos vegetales aptos
            pueden nutrir la huerta comunitaria.
          </p>
          <Link className="text-link" to="/educacion">
            Explorar guías ambientales <ArrowRight size={16} />
          </Link>
        </div>
        <div className="point-promo">
          <Coins />
          <h2>Conoce tus EcoPuntos</h2>
          <p>
            Consulta tus entregas y los puntos que obtuviste con cada pesaje
            confirmado.
          </p>
          <Link className="text-link" to="/verificar">
            Entrar a Mi EcoConecta <ArrowRight size={16} />
          </Link>
        </div>
      </section>
      <section className="impact-band" id="impacto">
        <div className="wrap section">
          <h2>Nuestro impacto</h2>
          <p>Consulta indicadores reales con la fecha del servidor.</p>
          <Link className="btn secondary" to="/resultados-diarios">
            Ver resultados diarios
          </Link>
        </div>
      </section>
      <section className="wrap section split">
        <h2>Preguntas frecuentes</h2>
        <div>
          {[
            [
              "¿Qué materiales puedo entregar?",
              "Reciclables limpios y secos y orgánicos aptos para huerta.",
            ],
            [
              "¿Cómo sé cuándo recogerán mis residuos?",
              "Consulta el código de tu solicitud para ver cuándo está programada.",
            ],
            [
              "¿Cuándo recibo EcoPuntos?",
              "Después de confirmar el peso real. Las equivalencias están pendientes de validación por la Fundación.",
            ],
          ].map(([q, a]) => (
            <details key={q}>
              <summary>{q}</summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>
      <section className="wrap section line">
        <h2>¿Listo para tu primera entrega?</h2>
        <WhatsAppLink>Solicitar por WhatsApp <ArrowRight size={17} /></WhatsAppLink>
      </section>
    </>
  );
}
function Classification({ onSelect }: { onSelect?: (g: Group) => void }) {
  const [choice, setChoice] = useState("");
  return (
    <>
      <div className="choice-grid">
        {[
          ...categories,
          [
            Search,
            "No estoy seguro",
            "Identifica primero el material con una guía ambiental.",
          ] as const,
        ].map(([Icon, label, info]) => (
          <button
            key={label}
            className={"choice " + (choice === label ? "selected" : "")}
            aria-pressed={choice === label}
            onClick={() => setChoice(label)}
          >
            <Icon size={22} />
            <strong>{label}</strong>
            <small>{info}</small>
          </button>
        ))}
      </div>
      {choice && (
        <div className="hint actions">
          {choice === "Orgánico" || choice === "Reciclable" ? (
            <>
              {choice === "Orgánico"
                ? "Colectivo de huerteros"
                : "Colectivo de recicladores"}
              {onSelect ? (
                <button
                  className="btn primary"
                  onClick={() => onSelect(choice)}
                >
                  Confirmar clasificación
                </button>
              ) : (
                <Link
                  className="btn primary"
                  to={"/solicitar?material=" + choice}
                >
                  Solicitar recolección
                </Link>
              )}
            </>
          ) : (
            <Link className="text-link" to="/educacion">
              Consultar orientación ambiental <ArrowRight size={16} />
            </Link>
          )}
        </div>
      )}
    </>
  );
}
export function Education() {
  const { state } = useDemo(),
    [filter, setFilter] = useState("");
  const articles = state.articles.filter(
    (a) => a.published && (!filter || a.category === filter),
  );
  return (
    <div className="wrap section">
      <Heading
        title="Educación ambiental"
        text="Guías para separar y aprovechar residuos en casa, en tu negocio y en la huerta."
      />
      <div className="education-cover">
        <img src="/comunidad.webp" alt="Huerta y reciclaje comunitario" />
        <div>
          <BookOpen />
          <h2>Empieza con lo que tienes en casa</h2>
        </div>
      </div>
      <div className="actions my-6">
        {["", "Comunidad", "Orgánico", "Reciclable"].map((s) => (
          <button
            key={s}
            aria-pressed={filter === s}
            className={"btn " + (filter === s ? "primary" : "secondary")}
            onClick={() => setFilter(s)}
          >
            {s || "Todas las guías"}
          </button>
        ))}
      </div>
      <div className="grid-three">
        {articles.map((a) => (
          <Panel title={a.title} key={a.id}>
            <p>{a.body}</p>
          </Panel>
        ))}
      </div>
      {!articles.length && <Empty>No hay guías en esta categoría.</Empty>}
    </div>
  );
}
export function Assistant() {
  const [mode, setMode] = useState(""),
    [photo, setPhoto] = useState<string>(),
    [group, setGroup] = useState<Group>(),
    [correct, setCorrect] = useState(false);
  return (
    <div className="wrap section narrow">
      <Heading
        title="Asistente EcoConecta"
        text="Simulación de WhatsApp y clasificación por imagen."
      />
      <section className="chat">
        <header>
          <MessageCircle />
          <strong>EcoConecta</strong>
          <small>Demostración</small>
        </header>
        <div className="chat-body">
          <div className="bubble">
            ¡Hola! Soy EcoConecta, tu asistente ambiental. ¿En qué puedo
            ayudarte hoy?
          </div>
          {!mode && (
            <div className="chat-menu">
              <button onClick={() => setMode("foto")}>
                <Camera size={18} /> Identificar residuo con foto
              </button>
              <button onClick={() => setMode("manual")}>
                <Recycle size={18} /> Solicitar recolección manual
              </button>
              <Link to="/consultar">
                <Search size={18} /> Consultar solicitud
              </Link>
              <Link to="/verificar">
                <Coins size={18} /> Consultar EcoPuntos
              </Link>
              <Link to="/educacion">
                <BookOpen size={18} /> Aprender sobre reciclaje
              </Link>
            </div>
          )}
          {mode === "manual" && <Classification />}
          {mode === "foto" && (
            <>
              <Form
                label={
                  photo
                    ? "Analizar otra imagen"
                    : "Preparar resultado de ejemplo"
                }
                onSave={async (data) => {
                  const image = await imageData(data.get("photo"));
                  if (!image) throw Error("Adjunta una fotografía.");
                  setGroup(undefined);
                  setCorrect(false);
                  await new Promise((resolve) => setTimeout(resolve, 450));
                  setPhoto(image);
                }}
              >
                <Field label="Fotografía">
                  <input
                    name="photo"
                    required
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                  />
                </Field>
              </Form>
              {photo && (
                <>
                  <img
                    className="upload-preview"
                    src={photo}
                    alt="Fotografía cargada"
                  />
                  <div className="bubble">
                    <strong>Resultado de ejemplo · Botella plástica</strong>
                    <p>
                      Reciclable · Potencialmente aprovechable · Colectivo de
                      recicladores.
                    </p>
                    <p>Vacía y seca el envase antes de entregarlo.</p>
                    <div className="actions">
                      <button
                        className="btn secondary"
                        onClick={() => {
                          setGroup("Reciclable");
                          setCorrect(false);
                        }}
                      >
                        Confirmar clasificación
                      </button>
                      <button
                        className="btn secondary"
                        onClick={() => {
                          setGroup(undefined);
                          setCorrect(true);
                        }}
                      >
                        Corregir
                      </button>
                    </div>
                  </div>
                  {correct && (
                    <Classification
                      onSelect={(g) => {
                        setGroup(g);
                        setCorrect(false);
                      }}
                    />
                  )}
                  {group && (
                    <Link
                      className="btn primary"
                      to={"/solicitar?material=" + group}
                      state={{
                        photo,
                        ai: "Botella plástica · Reciclable",
                        classification:
                          group === "Reciclable" ? "Botella plástica" : "",
                      }}
                    >
                      Solicitar recolección <ArrowRight size={16} />
                    </Link>
                  )}
                </>
              )}
            </>
          )}
          {mode && (
            <button className="text-link" onClick={() => setMode("")}>
              Volver al menú
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
export function IntakePage() {
  const { state, actor, save } = useDemo(),
    [params] = useSearchParams(),
    location = useLocation();
  const person =
    actor && isResident(actor.role)
      ? state.people.find((p) => p.id === actor.id)
      : undefined;
  const initial = location.state as {
    photo?: string;
    ai?: string;
    classification?: string;
  } | null;
  const [step, setStep] = useState(0),
    [code, setCode] = useState(""),
    [serverId, setServerId] = useState<number>();
  const [draft, setDraft] = useState<Intake>({
    name: person?.name ?? "",
    phone: person?.phone ?? "",
    generator: person?.role === "negocio" ? "negocio" : "hogar",
    sector: state.settings.sector,
    address: person?.address ?? "",
    references: "",
    group: params.get("material") === "Orgánico" ? "Orgánico" : "Reciclable",
    classification: initial?.classification ?? "",
    description: "",
    preferred: person?.availability || "Mañana",
    notes: "",
    photo: initial?.photo,
    ai: initial?.ai,
  });
  if (!apiToken())
    return (
      <div className="wrap section narrow">
        <Heading title="Inicia sesión para solicitar" text="Las solicitudes se guardan en tu cuenta registrada." />
        <Panel>
          <Link className="btn primary" to="/acceso-registrado">Iniciar sesión</Link>
        </Panel>
      </div>
    );
  if (code)
    return (
      <div className="wrap section narrow">
        <Panel>
          <CalendarCheck size={32} />
          <Heading
            title="Solicitud recibida"
            text="Guarda el código para consultar tu solicitud."
          />
          <p className="request-code">{code}</p>
          <Badge status="Recibida" />
          <Link className="btn primary mt-5" to={serverId ? "/operacion/solicitud/" + serverId : "/consultar?codigo=" + code}>
            Consultar solicitud
          </Link>
        </Panel>
      </div>
    );
  return (
    <div className="wrap section narrow">
      <Heading
        title="Solicita una recolección"
        text="Completa los datos reales de tu solicitud."
      />
      <ol className="wizard">
        {["Contacto", "Material y horario", "Confirmar"].map((s, i) => (
          <li key={s} aria-current={step === i ? "step" : undefined}>
            <span>{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      <Panel>
        <Form
          key={step}
          label={step === 2 ? "Confirmar solicitud" : "Continuar"}
          onSave={async (d) => {
            if (step === 0) {
              const phone = normalizePhone(value(d, "phone"));
              if (!/^3\d{9}$/.test(phone))
                throw Error("Escribe un celular colombiano válido.");
              setDraft({
                ...draft,
                phone,
                name: value(d, "name"),
                generator: (person?.role ??
                  value(d, "generator")) as Intake["generator"],
                sector: value(d, "sector"),
                address: value(d, "address"),
                references: value(d, "references"),
              });
            }
            if (step === 1)
              setDraft({
                ...draft,
                group: value(d, "group") as Group,
                classification: value(d, "classification"),
                description: value(d, "description"),
                preferred: value(d, "preferred"),
                estimate: value(d, "estimate")
                  ? Number(value(d, "estimate"))
                  : undefined,
                notes: value(d, "notes"),
                photo: d.has("remove")
                  ? undefined
                  : ((await imageData(d.get("photo"))) ?? draft.photo),
              });
            if (step < 2) {
              setStep(step + 1);
              return;
            }
            if (apiToken()) {
              const materials = await materialService.list();
              const category = draft.group === "Orgánico" ? "organico" : "reciclable";
              const material = materials.find(
                (item: { categoria: string }) => item.categoria === category,
              );
              if (!material)
                throw Error("No hay un material activo para este tipo de residuo.");
              const created = await solicitudService.create({
                direccion: draft.address,
                descripcion: draft.description || draft.notes || draft.classification,
                horario_preferido: draft.preferred,
                materiales: [{
                  material_id: material.id,
                  estimado_kg: draft.estimate,
                  confirmado: true,
                }],
              });
              setCode(created.codigo);
              setServerId(created.id);
              return;
            }
          }}
        >
          {step === 0 && (
            <div className="form-grid">
              <Field label="Nombre o establecimiento">
                <input name="name" required defaultValue={draft.name} />
              </Field>
              <Field label="Celular">
                <input
                  name="phone"
                  type="tel"
                  required
                  defaultValue={draft.phone}
                />
              </Field>
              <Field label="Tipo de generador">
                <select
                  name="generator"
                  defaultValue={draft.generator}
                  disabled={!!person}
                >
                  <option value="hogar">Hogar</option>
                  <option value="negocio">Negocio</option>
                </select>
              </Field>
              <Field label="Sector">
                <input name="sector" required defaultValue={draft.sector} />
              </Field>
              <Field label="Dirección">
                <input name="address" required defaultValue={draft.address} />
              </Field>
              <Field label="Referencias (opcional)">
                <input name="references" defaultValue={draft.references} />
              </Field>
            </div>
          )}
          {step === 1 && (
            <>
              <div className="form-grid">
                <Field label="Tipo de residuo">
                  <select name="group" defaultValue={draft.group}>
                    <option>Reciclable</option>
                    <option>Orgánico</option>
                  </select>
                </Field>
                <Field label="Clasificación">
                  <input
                    name="classification"
                    placeholder="Ej. cartón limpio"
                    required
                    defaultValue={draft.classification}
                  />
                </Field>
                <Field label="Cantidad estimada en kg (opcional)">
                  <input
                    name="estimate"
                    type="number"
                    min=".01"
                    step="any"
                    defaultValue={draft.estimate}
                  />
                </Field>
                <Field label="Horario preferido">
                  <select name="preferred" defaultValue={draft.preferred}>
                    {[
                      ...new Set([
                        "Mañana",
                        "Tarde",
                        "Horario flexible",
                        draft.preferred,
                      ]),
                    ].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field label="Descripción del residuo">
                <textarea
                  name="description"
                  required
                  defaultValue={draft.description}
                />
              </Field>
              <Field label="Observaciones (opcional)">
                <textarea name="notes" defaultValue={draft.notes} />
              </Field>
              <Field label="Fotografía (opcional)">
                <input
                  name="photo"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                />
              </Field>
              {draft.photo && (
                <>
                  <img
                    className="upload-preview"
                    src={draft.photo}
                    alt="Fotografía adjunta"
                  />
                  <label>
                    <input type="checkbox" name="remove" /> Quitar fotografía
                  </label>
                </>
              )}
            </>
          )}
          {step === 2 && (
            <>
              <h2>Revisa tu solicitud</h2>
              <dl className="facts">
                {[
                  ["Nombre", draft.name],
                  ["Teléfono", draft.phone],
                  ["Generador", draft.generator],
                  ["Ubicación", draft.sector + " · " + draft.address],
                  ["Referencias", draft.references],
                  ["Material", draft.group + " · " + draft.classification],
                  ["Descripción", draft.description],
                  [
                    "Cantidad estimada",
                    draft.estimate ? draft.estimate + " kg" : "",
                  ],
                  ["Horario", draft.preferred],
                  ["Observaciones", draft.notes],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v || "—"}</dd>
                  </div>
                ))}
              </dl>
              {draft.photo && (
                <img
                  className="upload-preview"
                  src={draft.photo}
                  alt="Residuo adjunto"
                />
              )}
            </>
          )}
          {step > 0 && (
            <button
              className="text-link"
              type="button"
              onClick={() => setStep(step - 1)}
            >
              Atrás
            </button>
          )}
        </Form>
      </Panel>
    </div>
  );
}
export function Lookup() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get("codigo") ?? "");
  return (
    <div className="wrap section narrow">
      <Heading
        title="Consultar solicitud"
        text="El seguimiento privado requiere una cuenta residente autenticada."
      />
      <Panel>
        <Form
          label="Buscar solicitud"
          onSave={(d) => setQuery(value(d, "code"))}
        >
          <Field label="Código de solicitud">
            <input
              name="code"
              required
              defaultValue={query}
              placeholder="ECO-2026-001"
            />
          </Field>
        </Form>
      </Panel>
      {query && (
        <div className="mt-5">
          <Panel>
            <p>Inicia sesión para consultar el estado y el historial de tus solicitudes.</p>
            <Link className="text-link" to="/acceso-registrado">Acceder con mi cuenta</Link>
          </Panel>
        </div>
      )}
    </div>
  );
}
export function Access() {
  return (
    <div className="wrap section sign-in">
      <aside>
        <Leaf size={38} />
        <h1>Acceso al panel</h1>
        <p>
          Gestiona las recolecciones y el impacto ambiental de Villas de San
          Pablo.
        </p>
        <Link to="/verificar">
          Soy residente o negocio <ArrowRight size={17} />
        </Link>
        <Link className="text-link mt-4" to="/acceso-registrado">
          Acceder con una cuenta registrada <ArrowRight size={17} />
        </Link>
      </aside>
      <Panel title="Acceso autenticado">
        <p>Los roles se verifican con tu cuenta y el servidor FastAPI.</p>
        <Link className="btn primary" to="/acceso-registrado">Iniciar sesión</Link>
        <Link className="text-link mt-4" to="/crear-cuenta">Crear cuenta de residente</Link>
      </Panel>
    </div>
  );
}
export function CreateAccount() {
  const navigate = useNavigate();
  return (
    <div className="wrap section narrow">
      <Heading title="Crear cuenta" text="Tu cuenta se registrará como residente." />
      <Panel>
        <Form
          label="Registrarme"
          onSave={async (data) => {
            const password = String(data.get("password") ?? "");
            const confirm = String(data.get("confirm_password") ?? "");
            if (password !== confirm) throw Error("Las contraseñas no coinciden.");
            await authService.register({
              nombre: value(data, "nombre"),
              correo: value(data, "correo"),
              password,
              confirm_password: confirm,
              telefono: value(data, "telefono") || undefined,
              direccion: value(data, "direccion") || undefined,
              tipo_generador: value(data, "tipo_generador") as "hogar" | "negocio",
            });
            await authService.login({ correo: value(data, "correo"), password });
            navigate("/operacion", { replace: true });
          }}
        >
          <Field label="Nombre completo"><input name="nombre" required minLength={2} maxLength={120} /></Field>
          <Field label="Correo electrónico"><input name="correo" type="email" required autoComplete="email" /></Field>
          <Field label="Contraseña"><input name="password" type="password" required minLength={12} maxLength={256} autoComplete="new-password" /></Field>
          <Field label="Confirmar contraseña"><input name="confirm_password" type="password" required minLength={12} maxLength={256} autoComplete="new-password" /></Field>
          <Field label="Teléfono"><input name="telefono" type="tel" maxLength={20} /></Field>
          <Field label="Dirección"><input name="direccion" maxLength={1000} /></Field>
          <Field label="Tipo de generador">
            <select name="tipo_generador" defaultValue="hogar">
              <option value="hogar">Hogar</option>
              <option value="negocio">Negocio</option>
            </select>
          </Field>
        </Form>
      </Panel>
    </div>
  );
}
export function Verify() {
  return (
    <div className="wrap section narrow">
      <Heading
        title="Mi EcoConecta"
        text="Consulta solicitudes y EcoPuntos con tu cuenta registrada."
      />
      <Link className="btn primary mb-4" to="/acceso-registrado">Acceder con una cuenta registrada</Link>
      <div className="mt-5"><WhatsAppLink>Solicitar por WhatsApp</WhatsAppLink></div>
    </div>
  );
}
