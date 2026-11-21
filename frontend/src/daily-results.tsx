import { useEffect, useState } from "react";
import { CalendarCheck, Leaf, Recycle, Scale, Store, Users } from "lucide-react";
import { Field, Heading, Panel } from "./ui";
import { indicadoresService } from "./services";

type Result = Awaited<ReturnType<typeof indicadoresService.daily>>;
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const format = (value: number) => new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(value);

export function DailyResults({ allowDemoFallback = true }: { allowDemoFallback?: boolean }) {
  const [fecha, setFecha] = useState(today);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null);
    setError(false);
    indicadoresService.daily(fecha)
      .then((data) => { if (active) setResult(data); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [fecha, attempt, allowDemoFallback]);
  const report = result;
  const entries = report && [
    [Scale, "Material recolectado", `${format(report.total_kg)} kg`],
    [Recycle, "Reciclables", `${format(report.reciclables_kg)} kg`],
    [Leaf, "Orgánicos", `${format(report.organicos_kg)} kg`],
    [CalendarCheck, "Recolecciones confirmadas", format(report.recolecciones_confirmadas)],
    [Users, "Hogares participantes", format(report.hogares_participantes)],
    [Store, "Negocios participantes", format(report.negocios_participantes)],
  ] as const;
  return <div className="wrap section"><Heading title="Resultados diarios" text="Conoce las recolecciones confirmadas en Villas de San Pablo."/>
    <div className="daily-filter"><Field label="Fecha del reporte"><input type="date" value={fecha} max={today()} onChange={e => { if (e.target.value) setFecha(e.target.value); }}/></Field><p>Las fechas corresponden a la hora de Barranquilla.</p></div>
    {error ? <Panel><p role="alert">No se pudieron cargar los resultados del servidor.</p>
      <button type="button" className="btn secondary mt-3" onClick={() => setAttempt((count) => count + 1)}>Reintentar conexión</button>
    </Panel> : !report ? <Panel><p role="status">Cargando resultados…</p></Panel> : <>
      <p className="daily-update">Reporte del {report.fecha}{report.ultima_actualizacion && ` · Última recolección: ${new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Bogota" }).format(new Date(report.ultima_actualizacion))}`}</p>
      {report.recolecciones_confirmadas === 0 && <Panel><p>Todavía no se han registrado recolecciones confirmadas para esta fecha.</p></Panel>}
      <div className="daily-grid">{entries?.map(([Icon, label, value]) => <article className="daily-card" key={label}><Icon size={22}/><span>{label}</span><strong>{value}</strong></article>)}</div>
      <Panel title="Material recolectado por colectivo"><div className="daily-comparison">{[["Reciclables", report.reciclables_kg], ["Orgánicos", report.organicos_kg]].map(([label, value]) => <div key={label}><div><span>{label}</span><strong>{format(Number(value))} kg</strong></div><div className="daily-track"><span style={{ width: `${report.total_kg ? Number(value) / report.total_kg * 100 : 0}%` }}/></div></div>)}</div></Panel>
      </>}
  </div>;
}
