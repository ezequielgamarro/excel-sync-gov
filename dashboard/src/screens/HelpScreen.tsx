/**
 * Manual de usuario integrado: se muestra desde el sidebar (Preferencias → Ayuda).
 */

interface Section {
  title: string;
  body: JSX.Element;
}

const SECTIONS: Section[] = [
  {
    title: "¿Qué es este panel?",
    body: (
      <p>
        Panel de administración táctico del <strong>Informe Operativo Comparativo</strong> del
        Centro Integrador de Sistemas y Operaciones de la Policía de Tucumán. Muestra, en tiempo
        real, los indicadores agregados del operativo (consultas, aprehensiones, secuestros)
        distribuidos por unidad regional y tipo de incidente.
      </p>
    ),
  },
  {
    title: "Cómo leer las tarjetas KPI y sus variaciones",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li>
          El número grande es el <strong>valor actual</strong> del indicador.
        </li>
        <li>
          El chip de la derecha (▲/▼ + %) es la <strong>variación</strong> respecto al período de
          comparación activo; el pie muestra el valor de referencia y el delta absoluto.
        </li>
        <li>
          El selector <strong>Comparar vs</strong> (cabecera) cambia el período de referencia: Ayer,
          Semana anterior, Mes anterior o Año anterior.
        </li>
        <li>Color verde = sube, rojo = baja, sin flecha = sin cambios.</li>
      </ul>
    ),
  },
  {
    title: "Filtros: Unidad Regional y Rango",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li>
          <strong>Unidad Regional</strong>: «Todas» o el nombre oficial de la unidad (lista real
          devuelta por el backend).
        </li>
        <li>
          <strong>Rango</strong>: 24 h / 7 días / 30 días. Escala el volumen de los valores
          mostrados.
        </li>
        <li>Todos los gráficos y tablas se recalculan al instante de forma determinista.</li>
      </ul>
    ),
  },
  {
    title: "Selector de comparación temporal",
    body: (
      <p>
        Situado en la cabecera superior, permite comparar los KPI y las barras contra una ventana
        anterior (Ayer, Semana, Mes o Año). Además de la variación porcentual, la ventana ajusta la
        magnitud de los valores para reflejar el período.
      </p>
    ),
  },
  {
    title: "Estados de conexión",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li>
          <strong>EN VIVO</strong>: canal WebSocket activo y sincronizado (heartbeat cada 15 s).
        </li>
        <li>
          <strong>RECONECTANDO</strong>: se perdió el canal y se reintenta con backoff.
        </li>
        <li>
          <strong>DEGRADADO · POLLING</strong>: sin WSS, se refresca por REST cada 10 s.
        </li>
        <li>
          <strong>SIN CONEXIÓN</strong>: sesión no autorizada o revocada; vuelva a iniciar sesión.
        </li>
        <li>
          <strong>DATOS DESACTUALIZADOS</strong>: aviso cuando pasan más de 120 s sin sincronización
          real (heartbeat o nueva instantánea).
        </li>
      </ul>
    ),
  },
  {
    title: "Roles y capacidades",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li>
          <strong>viewer</strong>: solo lectura del dashboard en vivo (<code>dash.view.live</code>).
        </li>
        <li>
          <strong>supervisor</strong>: además histórico, exportación CSV y replay.
        </li>
        <li>
          <strong>auditor</strong>: histórico, exportación y auditoría (<code>audit.view</code>).
        </li>
        <li>
          <strong>platform-admin</strong>: administración de la plataforma (webhooks, usuarios,
          rotación de secretos) y también visualización en vivo.
        </li>
      </ul>
    ),
  },
];

export function HelpScreen(): JSX.Element {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div>
        <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
          Manual de uso
        </h2>
        <p className="text-sm text-muted">Guía rápida del panel operativo.</p>
      </div>
      {SECTIONS.map((section) => (
        <section key={section.title} className="panel">
          <h3 className="panel-title panel-title--cap mb-2">{section.title}</h3>
          <div className="text-sm leading-relaxed text-ink2">{section.body}</div>
        </section>
      ))}
    </div>
  );
}
