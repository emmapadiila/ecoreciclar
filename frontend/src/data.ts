import {
  dateKey,
  groups,
  roles,
  type State,
  type Role,
  type Request,
  type Article,
} from "./model.ts";

const lessons = [
  [
    "Aprende a reciclar",
    "Separa los envases de papel, plástico, metal y vidrio. Límpialos y sécalos antes de entregarlos.",
  ],
  [
    "Residuos orgánicos",
    "Aparta cáscaras, frutas y restos de verduras. Evita mezclar aceites, carne o empaques con los residuos para huerta.",
  ],
  [
    "Residuos reciclables",
    "Mantén el cartón seco y aplana los envases limpios para ahorrar espacio. Envuelve el vidrio roto y consulta la ruta adecuada.",
  ],
  [
    "Residuos no aprovechables",
    "Separa servilletas sucias, empaques contaminados y residuos sanitarios. Consulta al prestador de aseo sobre su disposición.",
  ],
  [
    "Compostaje",
    "Combina restos vegetales con hojas secas, remueve la mezcla y mantenla húmeda sin encharcarla.",
  ],
  [
    "Separación en casa",
    "Ubica recipientes diferenciados y enséñale a cada persona del hogar dónde depositar cada material.",
  ],
  [
    "Consejos para negocios",
    "Separa el cartón de la cocina, conserva los reciclables bajo techo y acuerda una franja de entrega con el colectivo.",
  ],
  [
    "Preguntas frecuentes",
    "La solicitud se programa con el colectivo. Los EcoPuntos se calculan después del pesaje confirmado.",
  ],
];
export const education: Article[] = lessons.map(([title, body], i) => ({
  id: "guia-" + i,
  title,
  body,
  category: i === 1 || i === 4 ? groups[1] : i === 2 ? groups[0] : "Comunidad",
  published: true,
}));
export function seed(): State {
  const people = (Object.keys(roles) as Role[]).map((role, i) => ({
    id: role,
    role,
    name: [
      "Camila Mendoza",
      "Diana Pacheco",
      "Luis Mercado",
      "Elena Herrera",
      "Andrea Salcedo",
      "Fundación Santo Domingo",
      "María Torres",
      "Tienda El Vecino",
    ][i],
    phone: "300000000" + i,
    active: true,
    pilot: true,
  }));
  const now = new Date();
  const at = (offset: number) =>
    new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() + offset,
      10,
    ).toISOString();
  const requests: Request[] = Array.from({ length: 16 }, (_, i) => {
    const group = groups[i % 2];
    const status = (
      [
        "Recibida",
        "Recolectada",
        "En revisión",
        "Programada",
        "Asignada",
        "Recolectada",
        "Programada",
        "Recibida",
        "Recolectada",
        "En revisión",
        "Recolectada",
        "Asignada",
        "Recolectada",
        "Programada",
        "Recibida",
        "Recolectada",
      ] as const
    )[i];
    const owner = i % 3 === 0 ? "negocio" : "hogar";
    const person = people.find((p) => p.id === owner)!;
    const created = at(-i * 4);
    const worker = group === "Reciclable" ? "reciclador" : "huertero";
    const assigned = ["Asignada", "Programada", "Recolectada"].includes(status);
    const scheduled = status === "Programada" || status === "Recolectada";
    const date = dateKey(
      new Date(at(status === "Recolectada" ? -i * 3 : i % 7)),
    );
    const history = [{ title: "Recibida", at: created, by: person.name }];
    if (status !== "Recibida")
      history.push({ title: "En revisión", at: created, by: "Coordinación" });
    if (assigned)
      history.push({ title: "Asignada", at: created, by: "Coordinación" });
    if (scheduled)
      history.push({ title: "Programada", at: created, by: "Coordinación" });
    if (status === "Recolectada")
      history.push({
        title: status,
        at: date + "T10:00:00",
        by: "Coordinación",
      });
    return {
      id: "ECO-" + now.getFullYear() + "-" + String(i + 1).padStart(3, "0"),
      owner,
      name: person.name,
      phone: person.phone,
      generator: owner,
      group,
      status,
      created,
      sector: "Villas de San Pablo",
      address: "Manzana " + (i + 2) + ", casa 04",
      references: "Frente a la zona verde",
      classification:
        group === "Reciclable"
          ? ["Botellas PET", "Cartón limpio", "Papel y envases"][i % 3]
          : "Restos vegetales",
      description: "Material separado y listo para entregar.",
      preferred: "Mañana",
      notes: "",
      estimate: i + 2,
      history,
      ...(assigned
        ? {
            worker,
            coordinator: group === "Reciclable" ? "reciclaje" : "huerta",
            assignedAt: created,
          }
        : {}),
      ...(scheduled ? { schedule: { date, time: "10:00", notes: "" } } : {}),
      ...(status === "Recolectada"
        ? {
            collection: {
              date,
              weight: i + 2.5,
              material:
                group === "Reciclable"
                  ? "Reciclables separados"
                  : "Restos vegetales",
              notes: "",
              result: "Aprovechable",
              rate: 10,
            },
          }
        : {}),
    };
  });
  return {
    people,
    requests,
    articles: education.map((a) => ({ ...a })),
    audit: [],
    rules: groups.map((group, i) => ({
      id: "rule-" + i,
      group,
      rate: 10,
      from: "2020-01-01",
      until: "",
      approved: true,
    })),
    movements: requests.flatMap((r) =>
      r.collection
        ? [
            {
              id: r.id + "-p",
              request: r.id,
              value: r.collection.weight * r.collection.rate,
              at: r.collection.date,
              reason: "Recolección confirmada",
            },
          ]
        : [],
    ),
    notices: requests
      .slice(0, 4)
      .map((r) => ({
        id: r.id + "-n",
        request: r.id,
        title: "Nueva solicitud",
        at: r.created,
        by: r.name,
        readBy: [],
      })),
    settings: {
      sector: "Villas de San Pablo",
      pilot: true,
      recycling: "Colectivo de recicladores",
      organic: "Colectivo de huerteros",
    },
  };
}
