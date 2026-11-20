import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  BarChart3,
  CalendarCheck,
  ClipboardList,
  Coins,
  Recycle,
  Scale,
  Sprout,
  Users,
} from "lucide-react";
import { useDemo } from "./store";
import { Badge, Empty, Field, Heading, Panel } from "./ui";
import {
  dateKey,
  dateLabel,
  groups,
  isResident,
  number,
  statuses,
  totalPoints,
  totalWeight,
  type Request,
} from "./model";

export function Stats({ entries }: { entries: [string, string | number][] }) {
  const icons = [
    ClipboardList,
    Scale,
    CalendarCheck,
    Recycle,
    Users,
    Sprout,
    Coins,
  ];
  return (
    <div className="stats">
      {entries.map(([label, value], i) => {
        const Icon = icons[i % icons.length];
        return (
          <div key={label}>
            <span className="metric-icon">
              <Icon size={19} />
            </span>
            <small>{label}</small>
            <strong>{value}</strong>
          </div>
        );
      })}
    </div>
  );
}
export function Chart({
  title,
  data,
  series,
}: {
  title: string;
  data: Record<string, string | number>[];
  series: string[];
}) {
  return (
    <Panel title={title}>
      {data.length ? (
        <>
          <div className="chart" aria-hidden="true">
            <ResponsiveContainer>
              <BarChart data={data} margin={{ left: -22, right: 8, top: 8 }}>
                <CartesianGrid stroke="#e1e9e3" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#52645a", fontSize: 11 }}
                  tickLine={false}
                  interval={0}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: "#52645a", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip />
                <Legend />
                {series.map((s, i) => (
                  <Bar
                    key={s}
                    dataKey={s}
                    fill={i === 0 ? "#168A2E" : "#0A9B70"}
                    radius={[5, 5, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details>
            <summary>Ver datos</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Periodo o categoría</th>
                    {series.map((s) => (
                      <th key={s}>{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.map((row) => (
                    <tr key={row.label}>
                      <th scope="row">{row.label}</th>
                      {series.map((s) => (
                        <td key={s}>{row[s]}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <Empty>No hay datos para este periodo.</Empty>
      )}
    </Panel>
  );
}
export function monthly(items: Request[]) {
  const months = new Map<
    string,
    { kg: number; entregas: number; hogares: number; negocios: number }
  >();
  for (const item of items) {
    if (!item.collection) continue;
    const month = item.collection.date.slice(0, 7),
      row = months.get(month) ?? {
        kg: 0,
        entregas: 0,
        hogares: 0,
        negocios: 0,
      };
    row.kg += item.collection.weight;
    row.entregas++;
    row[item.generator === "hogar" ? "hogares" : "negocios"]++;
    months.set(month, row);
  }
  return [...months.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, row]) => ({
      label: month,
      ...row,
      kg: Number(row.kg.toFixed(3)),
    }));
}
export function Impact({ items }: { items: Request[] }) {
  const { state } = useDemo();
  const [filters, setFilters] = useState({
    from: "",
    until: "",
    group: "",
    generator: "",
    status: "",
  });
  const data = items.filter((r) => {
    const d = (r.collection?.date ?? r.created).slice(0, 10);
    return (
      (!filters.from || d >= filters.from) &&
      (!filters.until || d <= filters.until) &&
      (!filters.group || r.group === filters.group) &&
      (!filters.generator || r.generator === filters.generator) &&
      (!filters.status || r.status === filters.status)
    );
  });
  const weights = totalWeight(data),
    count = (g: string) =>
      new Set(data.filter((r) => r.generator === g).map((r) => r.owner)).size;
  const series = monthly(data);
  return (
    <>
      <Heading
        title="Indicadores EcoImpacto"
        text="Datos ficticios. Los totales de material se calculan con pesajes confirmados."
      />
      <div className="filters mb-5">
        {(
          [
            ["from", "Desde", null],
            ["until", "Hasta", null],
            ["group", "Colectivo", groups],
            ["generator", "Generador", ["hogar", "negocio"]],
            ["status", "Estado", statuses],
          ] as const
        ).map(([key, label, options]) => (
          <Field key={key} label={label}>
            {options ? (
              <select
                value={filters[key]}
                onChange={(e) =>
                  setFilters({ ...filters, [key]: e.target.value })
                }
              >
                <option value="">Todos</option>
                {options.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            ) : (
              <input
                type="date"
                value={filters[key]}
                onChange={(e) =>
                  setFilters({ ...filters, [key]: e.target.value })
                }
              />
            )}
          </Field>
        ))}
      </div>
      <Stats
        entries={[
          ["Kilogramos", number(weights) + " kg"],
          ["Toneladas", number(weights / 1000) + " t"],
          ["Confirmadas", data.filter((r) => r.collection).length],
          [
            "Pendientes",
            data.filter((r) => !["Recolectada", "Cancelada"].includes(r.status))
              .length,
          ],
          ["Hogares", count("hogar")],
          ["Negocios", count("negocio")],
          ["EcoPuntos", number(totalPoints(state, data))],
        ]}
      />
      <div className="chart-grid">
        <Chart title="Kilogramos por mes" data={series} series={["kg"]} />
        <Chart
          title="Orgánicos y reciclables"
          data={groups.map((g) => ({
            label: g,
            kg: totalWeight(data.filter((r) => r.group === g)),
          }))}
          series={["kg"]}
        />
        <Chart
          title="Solicitudes por estado"
          data={statuses.map((s) => ({
            label: s,
            solicitudes: data.filter((r) => r.status === s).length,
          }))}
          series={["solicitudes"]}
        />
        <Chart
          title="Recolecciones por periodo"
          data={series}
          series={["entregas"]}
        />
        <Chart
          title="Participación de hogares y negocios"
          data={[
            { label: "Hogares", participantes: count("hogar") },
            { label: "Negocios", participantes: count("negocio") },
          ]}
          series={["participantes"]}
        />
        <Chart
          title="Frecuencia mensual de entregas"
          data={series}
          series={["hogares", "negocios"]}
        />
      </div>
    </>
  );
}
export function Overview({ items, base }: { items: Request[]; base: string }) {
  const { state, actor } = useDemo(),
    who = actor!,
    me = state.people.find((p) => p.id === who.id);
  const resident = isResident(who.role),
    organic = who.role === "huerta";
  const completed = items
    .filter((r) => r.collection)
    .sort((a, b) => b.collection!.date.localeCompare(a.collection!.date));
  return (
    <>
      <Heading
        title={
          resident
            ? "Mi resumen"
            : who.role === "admin"
              ? "Dashboard"
              : organic
                ? "Panel de huerta"
                : "Panel de reciclaje"
        }
        text={
          resident
            ? "Consulta tus entregas, solicitudes y EcoPuntos."
            : "Revisa el estado de las recolecciones y las entregas confirmadas."
        }
      />
      <div className="dashboard-banner">
        <div>
          <h2>
            {resident
              ? "Hola, " + me?.name
              : organic
                ? "Residuos orgánicos y compostaje"
                : "Gestiona las recolecciones"}
          </h2>
          <p>
            {resident
              ? "Cada entrega cuenta para tu comunidad."
              : "Villas de San Pablo · Operación de demostración"}
          </p>
        </div>
        {organic ? <Sprout /> : <Recycle />}
      </div>
      <Stats
        entries={
          resident
            ? [
                [
                  "Solicitudes activas",
                  items.filter(
                    (r) => !["Recolectada", "Cancelada"].includes(r.status),
                  ).length,
                ],
                ["Completadas", completed.length],
                ["Material entregado", number(totalWeight(items)) + " kg"],
                ["EcoPuntos", number(totalPoints(state, items))],
                ["Última entrega", dateLabel(completed[0]?.collection?.date)],
              ]
            : [
                [
                  "Solicitudes nuevas",
                  items.filter((r) => r.status === "Recibida").length,
                ],
                [
                  "Pendientes de asignación",
                  items.filter((r) => r.status === "En revisión").length,
                ],
                [
                  "Asignadas",
                  items.filter((r) => r.status === "Asignada").length,
                ],
                [
                  "Programadas",
                  items.filter((r) => r.status === "Programada").length,
                ],
                ["Completadas", completed.length],
                ["Kilogramos", number(totalWeight(items)) + " kg"],
                ["EcoPuntos", number(totalPoints(state, items))],
              ]
        }
      />
      <div className="chart-grid">
        <Chart
          title={
            resident ? "Mis entregas por mes" : "Material recolectado por mes"
          }
          data={monthly(items)}
          series={["kg"]}
        />
        <Panel title="Solicitudes recientes">
          {items.length ? (
            <ul className="activity">
              {[...items]
                .sort((a, b) => b.created.localeCompare(a.created))
                .slice(0, 5)
                .map((r) => (
                  <li key={r.id}>
                    <Link to={base + "/solicitud/" + r.id}>
                      <strong>{r.id}</strong>
                      <small>{r.classification}</small>
                    </Link>
                    <Badge status={r.status} />
                  </li>
                ))}
            </ul>
          ) : (
            <Empty>Aún no hay solicitudes.</Empty>
          )}
          <Link className="text-link" to={base + "/solicitudes"}>
            Ver todas las solicitudes
          </Link>
        </Panel>
      </div>
      {resident && (
        <Panel title="Recomendación ambiental">
          <p>Separa los envases limpios y secos de los restos vegetales.</p>
          <Link className="text-link" to="/educacion">
            Consultar guías ambientales
          </Link>
        </Panel>
      )}
    </>
  );
}
export function Points({ items, base }: { items: Request[]; base: string }) {
  const { state, actor } = useDemo(),
    ids = new Set(items.map((r) => r.id)),
    moves = state.movements.filter((m) => ids.has(m.request)),
    done = items.filter((r) => r.collection),
    last = done
      .map((r) => r.collection!.date)
      .sort()
      .at(-1);
  const month = dateKey().slice(0, 7);
  return (
    <>
      <Heading
        title="EcoPuntos"
        text="Equivalencias ficticias pendientes de validación por la Fundación."
      />
      <Stats
        entries={[
          ["Saldo de EcoPuntos", number(totalPoints(state, items))],
          ["Kilogramos entregados", number(totalWeight(items)) + " kg"],
          ["Recolecciones", done.length],
          ["Última entrega", dateLabel(last)],
          [
            "EcoPuntos del mes",
            number(
              moves
                .filter((m) => m.at.startsWith(month))
                .reduce((sum, m) => sum + m.value, 0),
            ),
          ],
        ]}
      />
      {actor?.role === "admin" && (
        <Link className="btn secondary mb-5" to={base + "/reglas"}>
          Configurar reglas
        </Link>
      )}
      <Panel title="Movimientos">
        {moves.length ? (
          <ul className="activity">
            {moves.map((m) => (
              <li key={m.id}>
                <Link to={base + "/solicitud/" + m.request}>
                  <strong>
                    {m.request} · {m.reason}
                  </strong>
                  <small>{dateLabel(m.at)}</small>
                </Link>
                <strong className="point-value">
                  {m.value > 0 ? "+" : ""}
                  {number(m.value)} puntos
                </strong>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Los movimientos aparecerán al confirmar el pesaje.</Empty>
        )}
      </Panel>
    </>
  );
}
export function Notifications({
  items,
  base,
}: {
  items: Request[];
  base: string;
}) {
  const { state, actor, save } = useDemo(),
    who = actor!;
  const [filter, setFilter] = useState(""),
    [selected, setSelected] = useState("");
  const ids = new Set(items.map((r) => r.id)),
    notices = state.notices.filter((n) => ids.has(n.request)),
    notice = notices.find((n) => n.id === selected);
  return (
    <>
      <Heading
        title="Notificaciones"
        text="Actividad interna de la demostración. Los avisos de WhatsApp son simulados."
      />
      <div className="chart-grid">
        <Panel>
          <Field label="Tipo">
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">Todos los tipos</option>
              {[...new Set(notices.map((n) => n.title))].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          {notices.some((n) => !filter || n.title === filter) ? (
            <ul className="activity">
              {notices
                .filter((n) => !filter || n.title === filter)
                .map((n) => (
                  <li key={n.id}>
                    <button
                      className="text-link"
                      onClick={() => {
                        setSelected(n.id);
                        if (!n.readBy.includes(who.id))
                          save((s) => ({
                            ...s,
                            notices: s.notices.map((x) =>
                              x.id === n.id
                                ? {
                                    ...x,
                                    readBy: [...new Set([...x.readBy, who.id])],
                                  }
                                : x,
                            ),
                          }));
                      }}
                    >
                      {n.title} · {n.request}
                    </button>
                    <small>
                      {n.readBy.includes(who.id) ? "Leída" : "Sin leer"}
                    </small>
                  </li>
                ))}
            </ul>
          ) : (
            <Empty>No hay notificaciones.</Empty>
          )}
        </Panel>
        <Panel title="Detalle">
          {notice ? (
            <>
              <p>
                {notice.title} · {dateLabel(notice.at)}
              </p>
              <p>{notice.note}</p>
              <Link
                className="text-link"
                to={base + "/solicitud/" + notice.request}
              >
                Ver solicitud
              </Link>
            </>
          ) : (
            <Empty>Selecciona una notificación.</Empty>
          )}
        </Panel>
      </div>
    </>
  );
}
