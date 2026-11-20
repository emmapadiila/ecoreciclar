import { useEffect, useState } from "react";
import { CalendarCheck, Leaf, Recycle, Scale, Store, Users } from "lucide-react";
import { Field, Heading, Panel } from "./ui";
import { indicadoresService } from "./services";

type Result = Awaited<ReturnType<typeof indicadoresService.daily>>;
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const format = (value: number) => new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(value);

export function DailyResults() {
  const [fecha, setFecha] = useState(today);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setResult(null); setError(false);
    indicadoresService.daily(fecha).then(data => { if (active) setResult(data); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [fecha]);
  const entries = result && [
    [Scale, "Material recolectado", `${format(result.total_kg)} kg`],
    [Recycle, "Reciclables", `${format(result.reciclables_kg)} kg`],
    [Leaf, "Orgánicos", `${format(result.organicos_kg)} kg`],
    [CalendarCheck, "Recolecciones confirmadas", format(result.recolecciones_confirmadas)],
    [Users, "Hogares participantes", format(result.hogares_participantes)],
    [Store, "Negocios participantes", format(result.negocios_participantes)],
  ] as const;
  return <div className="wrap section"><Heading title="Resultados diarios" text="Conoce las recolecciones confirmadas en Villas de San Pablo."/>
    <div className="daily-filter"><Field label="Fecha del reporte"><input type="date" value={fecha} max={today()} onChange={e => { if (e.target.value) setFecha(e.target.value); }}/></Field><p>Las fechas corresponden a la hora de Barranquilla.</p></div>
    {error ? <Panel><p role="alert">No fue posible consultar los resultados. Comprueba tu conexión e inténtalo de nuevo.</p><button className="btn secondary" onClick={() => { setError(false); indicadoresService.daily(fecha).then(setResult).catch(() => setError(true)); }}>Reintentar</button></Panel>
      : !result ? <Panel><p role="status">Cargando resultados…</p></Panel> : <>
      <p className="daily-update">Reporte del {result.fecha} · {result.ultima_actualizacion ? `Última recolección: ${new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Bogota" }).format(new Date(result.ultima_actualizacion))}` : "Sin recolecciones registradas"}</p>
      {result.recolecciones_confirmadas === 0 && <Panel><p>Todavía no se han registrado recolecciones confirmadas para esta fecha.</p></Panel>}
      <div className="daily-grid">{entries?.map(([Icon, label, value]) => <article className="daily-card" key={label}><Icon size={22}/><span>{label}</span><strong>{value}</strong></article>)}</div>
      <Panel title="Material recolectado por colectivo"><div className="daily-comparison">{[["Reciclables", result.reciclables_kg], ["Orgánicos", result.organicos_kg]].map(([label, value]) => <div key={label}><div><span>{label}</span><strong>{format(Number(value))} kg</strong></div><div className="daily-track"><span style={{ width: `${result.total_kg ? Number(value) / result.total_kg * 100 : 0}%` }}/></div></div>)}</div></Panel>
      </>}
  </div>;
}
