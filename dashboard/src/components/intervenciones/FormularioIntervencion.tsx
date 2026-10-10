/**
 * Formulario reutilizable del NUEVO formato de intervenciones.
 *
 * Renderiza el mismo conjunto de campos de «Carga de Datos» (fecha con
 * `<input type="date">`, `mini_resena` con `<textarea>`, `select` estrictos para
 * los catálogos cerrados y textos libres para el resto). Se usa tanto en la
 * carga como en la edición del historial.
 *
 * Campos condicionales:
 * - Vehículo / Arma de fuego → subtipo (`detalle_tipo`) y, elegido el subtipo,
 *   el detalle «Tipo / Modelo / Calibre / N° de serie» (`detalle_identificacion`).
 *   Elemento muestra solo el detalle.
 * - Persona + Positivo → «Causas» es un desplegable; en cualquier otro caso es
 *   texto libre.
 * - Jefatura: Unidad Regional (habilita dependencias) o Dirección (sin ellas).
 *
 * El estado interno se sincroniza con `valoresIniciales` (al abrir el modal con
 * otra fila) y `fecha_consulta` vacía se envía como `null`.
 */

import { useEffect, useState, type FormEvent } from "react";
import type { IntervencionCreate } from "../../data/api";
import {
  CAUSAS_PERSONA_POSITIVO,
  DIRECCIONES,
  JERARQUIAS,
  SUBTIPOS_ARMA,
  SUBTIPOS_VEHICULO,
  UNIDADES_REGIONALES,
  DEPENDENCIAS_POR_REGIONAL,
  esDireccion,
} from "../../data/dependencias";

/** Valores del formulario: todos los campos son texto (fecha vacía = `""`). */
export interface FormValuesIntervencion
  extends Required<Omit<IntervencionCreate, "fecha_consulta">> {
  fecha_consulta: string;
}

/** Estado inicial del formulario: todos los campos vacíos. */
export const FORM_INICIAL: FormValuesIntervencion = {
  fecha_consulta: "",
  hora_consulta: "",
  jerarquia: "",
  personal_policial: "",
  jefatura_regional: "",
  dependencia: "",
  tipo_consulta: "",
  identificacion: "",
  detalle_tipo: "",
  resultado_consulta: "",
  causas: "",
  numero_registro: "",
  autoridad_judicial: "",
  sistema_utilizado: "",
  tramite_devuelto: "",
  hora_respuesta: "",
  personal_informa: "",
  cargo_informa: "",
  operativo_preventivo: "",
  allanamiento: "",
  mini_resena: "",
  legajo: "",
  lugar_hecho: "",
  detalle_identificacion: "",
};

const TIPOS_CONSULTA = ["Persona", "Vehículo", "Arma de fuego", "Elemento"] as const;
const RESULTADOS_CONSULTA = ["Positivo", "Negativo"] as const;
export const SISTEMAS_UTILIZADOS = [
  "División Antecedentes Personales",
  "División Verificación de Dominio",
  "División REPAR",
  "División SIFCOP",
  "Interpol",
  "Plataforma Ministerio Público Fiscal",
] as const;
const TRAMITES_DEVUELTOS = ["Sí", "No"] as const;
const RESULTADOS_ACTUACION = ["Positivo", "Negativo"] as const;
const TIPOS_ACTUACION = ["Operativo", "Allanamiento"] as const;

type TipoActuacion = (typeof TIPOS_ACTUACION)[number] | "";

/** Subtipos por tipo de consulta (los que no figuran no tienen subtipo). */
const SUBTIPOS_POR_CONSULTA: Record<string, readonly string[]> = {
  Vehículo: SUBTIPOS_VEHICULO,
  "Arma de fuego": SUBTIPOS_ARMA,
};

const INPUT_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm text-ink transition-colors focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-50";

interface FieldProps {
  label: string;
  children: JSX.Element;
}

function Field({ label, children }: FieldProps): JSX.Element {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs uppercase tracking-wide text-muted">
      <span className="truncate">{label}</span>
      {children}
    </label>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "time";
}

function TextField({ label, value, onChange, type = "text" }: TextFieldProps): JSX.Element {
  return (
    <Field label={label}>
      <input
        className={INPUT_CLASS}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

interface SelectFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly string[];
  placeholder: string;
  disabled?: boolean;
  required?: boolean;
}

function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
  required = false,
}: SelectFieldProps): JSX.Element {
  return (
    <Field label={label}>
      <select
        className={INPUT_CLASS}
        value={value}
        disabled={disabled}
        required={required}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </Field>
  );
}

interface RadioGroupProps {
  legend: string;
  name: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  /** Valor guardado que equivale a una opción (p. ej. «Sí» legacy = «Positivo»). */
  esActual?: (option: string, value: string) => boolean;
}

function RadioGroup({
  legend,
  name,
  value,
  options,
  onChange,
  esActual = (option, actual) => option === actual,
}: RadioGroupProps): JSX.Element {
  return (
    <fieldset className="flex min-w-0 flex-col gap-1 text-xs uppercase tracking-wide text-muted">
      <legend className="mb-1">{legend}</legend>
      <div className="flex flex-wrap gap-4">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm normal-case text-ink">
            <input
              type="radio"
              name={name}
              value={option}
              checked={esActual(option, value)}
              onChange={() => onChange(option)}
            />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * Antepone `actual` a `opciones` si trae un valor fuera del catálogo (datos
 * legacy). Así la edición no pierde el valor guardado y, aun así, el usuario
 * solo puede elegir valores del catálogo.
 */
function opcionesConActual(
  opciones: readonly string[],
  actual: string,
): readonly string[] {
  return actual !== "" && !opciones.includes(actual) ? [actual, ...opciones] : opciones;
}

/** Lookup seguro: la jefatura legacy no está en el catálogo y no debe romper. */
const CATALOGO_DEPENDENCIAS: Record<string, readonly string[]> = DEPENDENCIAS_POR_REGIONAL;

/** Equivalencia de valores legacy («Sí»/«No») con Positivo/Negativo. */
function esResultadoActuacion(option: string, actual: string): boolean {
  return (
    option === actual ||
    (option === "Positivo" && actual === "Sí") ||
    (option === "Negativo" && actual === "No")
  );
}

/** «Causas» es un desplegable solo para Persona con resultado Positivo. */
function causasEsLista(f: Pick<FormValuesIntervencion, "tipo_consulta" | "resultado_consulta">): boolean {
  return f.tipo_consulta === "Persona" && f.resultado_consulta === "Positivo";
}

/** Operativo si hay valor en `operativo_preventivo`; Allanamiento si en `allanamiento`. */
function inferirActuacion(f: FormValuesIntervencion): TipoActuacion {
  if (f.operativo_preventivo) return "Operativo";
  if (f.allanamiento) return "Allanamiento";
  return "";
}

/** Rellena con `""` lo que venga nulo/ausente (filas viejas sin las columnas nuevas). */
function completar(valores: FormValuesIntervencion): FormValuesIntervencion {
  const out = { ...FORM_INICIAL };
  for (const clave of Object.keys(FORM_INICIAL) as (keyof FormValuesIntervencion)[]) {
    out[clave] = (valores[clave] ?? "") as string;
  }
  return out;
}

export interface FormularioIntervencionProps {
  /** Valores con los que se resetea el formulario (cambia al abrir otra fila). */
  valoresIniciales: FormValuesIntervencion;
  /** Recibe el cuerpo listo para enviar (con `fecha_consulta` normalizada). */
  onSubmit: (payload: IntervencionCreate) => void | Promise<void>;
  /** Deshabilita el botón mientras hay una petición en vuelo. */
  enviando?: boolean;
  /** Texto del botón en reposo. */
  textoBoton?: string;
  /** Texto del botón mientras envía. */
  textoEnviando?: string;
}

export function FormularioIntervencion({
  valoresIniciales,
  onSubmit,
  enviando = false,
  textoBoton = "Guardar Reporte",
  textoEnviando = "Guardando…",
}: FormularioIntervencionProps): JSX.Element {
  const [form, setForm] = useState<FormValuesIntervencion>(() => completar(valoresIniciales));
  const [actuacion, setActuacion] = useState<TipoActuacion>(() =>
    inferirActuacion(completar(valoresIniciales)),
  );

  // Reset del estado interno cuando el padre entrega otros valores (p. ej. al
  // abrir el modal con otra fila del historial).
  useEffect(() => {
    const completos = completar(valoresIniciales);
    setForm(completos);
    setActuacion(inferirActuacion(completos));
  }, [valoresIniciales]);

  const setCampo = (key: keyof FormValuesIntervencion, value: string): void => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // Al cambiar tipo/resultado se descartan subtipo, detalle y causas que ya no
  // aplican, para no guardar combinaciones incoherentes.
  const setTipoConsulta = (value: string): void => {
    setForm((prev) => {
      const next = { ...prev, tipo_consulta: value, detalle_tipo: "", detalle_identificacion: "" };
      return causasEsLista(prev) !== causasEsLista(next) ? { ...next, causas: "" } : next;
    });
  };

  const setResultado = (value: string): void => {
    setForm((prev) => {
      const next = { ...prev, resultado_consulta: value };
      return causasEsLista(prev) !== causasEsLista(next) ? { ...next, causas: "" } : next;
    });
  };

  // Cascada Regional → Dependencia: al cambiar de jefatura se resetea la
  // dependencia para evitar combinaciones inválidas. Las Direcciones no tienen
  // dependencias.
  const setJefatura = (value: string): void => {
    setForm((prev) => ({ ...prev, jefatura_regional: value, dependencia: "" }));
  };

  // Operativo / Allanamiento: solo uno de los dos campos guarda el resultado.
  const setTipoActuacion = (value: string): void => {
    setActuacion(value as TipoActuacion);
    setForm((prev) => ({ ...prev, operativo_preventivo: "", allanamiento: "" }));
  };

  const setResultadoActuacion = (value: string): void => {
    const columna = actuacion === "Operativo" ? "operativo_preventivo" : "allanamiento";
    setCampo(columna, value);
  };

  const valorActuacion = actuacion === "Operativo" ? form.operativo_preventivo : form.allanamiento;

  const esDir = esDireccion(form.jefatura_regional);
  const regionalLegacy =
    form.jefatura_regional !== "" &&
    !esDir &&
    !(UNIDADES_REGIONALES as readonly string[]).includes(form.jefatura_regional);
  const dependencias = opcionesConActual(
    CATALOGO_DEPENDENCIAS[form.jefatura_regional] ?? [],
    form.dependencia,
  );

  const subtipos = SUBTIPOS_POR_CONSULTA[form.tipo_consulta];
  const mostrarDetalle =
    form.tipo_consulta === "Elemento" || (subtipos !== undefined && form.detalle_tipo !== "");

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const payload: IntervencionCreate = {
      ...form,
      fecha_consulta: form.fecha_consulta ? form.fecha_consulta : null,
    };
    void onSubmit(payload);
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Carga de intervención"
      className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2"
    >
      <section className="panel xl:col-span-2">
        <h3 className="panel-title panel-title--cap mb-3">Consulta</h3>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-3">
          <Field label="Fecha de consulta">
            <input
              className={INPUT_CLASS}
              type="date"
              value={form.fecha_consulta}
              onChange={(event) => setCampo("fecha_consulta", event.target.value)}
            />
          </Field>
          <TextField
            label="Hora de consulta"
            type="time"
            value={form.hora_consulta}
            onChange={(value) => setCampo("hora_consulta", value)}
          />
          <SelectField
            label="Tipo de consulta"
            value={form.tipo_consulta}
            onChange={setTipoConsulta}
            options={opcionesConActual(TIPOS_CONSULTA, form.tipo_consulta)}
            placeholder="Seleccionar…"
          />
          {subtipos && (
            <SelectField
              label={form.tipo_consulta === "Arma de fuego" ? "Tipo de arma" : "Tipo de vehículo"}
              value={form.detalle_tipo}
              onChange={(value) => setCampo("detalle_tipo", value)}
              options={opcionesConActual(subtipos, form.detalle_tipo)}
              placeholder="Seleccionar…"
            />
          )}
          {mostrarDetalle && (
            <TextField
              label="Tipo / Modelo / Calibre / N° de serie"
              value={form.detalle_identificacion}
              onChange={(value) => setCampo("detalle_identificacion", value)}
            />
          )}
          <TextField
            label="Identificación"
            value={form.identificacion}
            onChange={(value) => setCampo("identificacion", value)}
          />
          <SelectField
            label="Resultado"
            value={form.resultado_consulta}
            onChange={setResultado}
            options={RESULTADOS_CONSULTA}
            placeholder="Seleccionar…"
          />
          <SelectField
            label="Sistema utilizado"
            value={form.sistema_utilizado}
            onChange={(value) => setCampo("sistema_utilizado", value)}
            options={SISTEMAS_UTILIZADOS}
            placeholder="Seleccionar…"
          />
          <SelectField
            label="Trámite devuelto"
            value={form.tramite_devuelto}
            onChange={(value) => setCampo("tramite_devuelto", value)}
            options={TRAMITES_DEVUELTOS}
            placeholder="Seleccionar…"
          />
          <TextField
            label="Hora de respuesta"
            type="time"
            value={form.hora_respuesta}
            onChange={(value) => setCampo("hora_respuesta", value)}
          />
          <TextField
            label="N° de registro"
            value={form.numero_registro}
            onChange={(value) => setCampo("numero_registro", value)}
          />
        </div>
      </section>

      <section className="panel">
        <h3 className="panel-title panel-title--cap mb-3">Personal Interviniente</h3>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-3">
          <SelectField
            label="Jerarquía"
            value={form.jerarquia}
            onChange={(value) => setCampo("jerarquia", value)}
            options={opcionesConActual(JERARQUIAS, form.jerarquia)}
            placeholder="Seleccionar…"
          />
          <TextField
            label="Personal policial"
            value={form.personal_policial}
            onChange={(value) => setCampo("personal_policial", value)}
          />
          <TextField
            label="Legajo"
            value={form.legajo}
            onChange={(value) => setCampo("legajo", value)}
          />
          <Field label="Jefatura regional / Dirección">
            <select
              className={INPUT_CLASS}
              value={form.jefatura_regional}
              required
              onChange={(event) => setJefatura(event.target.value)}
            >
              <option value="">Seleccionar…</option>
              {regionalLegacy && (
                <option value={form.jefatura_regional}>{form.jefatura_regional}</option>
              )}
              <optgroup label="Unidades Regionales">
                {UNIDADES_REGIONALES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Direcciones">
                {DIRECCIONES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </optgroup>
            </select>
          </Field>
          <SelectField
            label="Dependencia"
            value={form.dependencia}
            onChange={(value) => setCampo("dependencia", value)}
            options={dependencias}
            placeholder={
              esDir
                ? "Sin dependencias"
                : form.jefatura_regional
                  ? "Seleccionar…"
                  : "Elija una jefatura…"
            }
            disabled={!form.jefatura_regional || esDir}
            required={Boolean(form.jefatura_regional) && !esDir}
          />
          <TextField
            label="Lugar del hecho"
            value={form.lugar_hecho}
            onChange={(value) => setCampo("lugar_hecho", value)}
          />
        </div>
      </section>

      <section className="panel">
        <h3 className="panel-title panel-title--cap mb-3">Actuación</h3>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-3">
          {causasEsLista(form) ? (
            <SelectField
              label="Causas"
              value={form.causas}
              onChange={(value) => setCampo("causas", value)}
              options={opcionesConActual(CAUSAS_PERSONA_POSITIVO, form.causas)}
              placeholder="Seleccionar…"
            />
          ) : (
            <TextField
              label="Causas"
              value={form.causas}
              onChange={(value) => setCampo("causas", value)}
            />
          )}
          <TextField
            label="Autoridad judicial"
            value={form.autoridad_judicial}
            onChange={(value) => setCampo("autoridad_judicial", value)}
          />
          <RadioGroup
            legend="Actuación"
            name="tipo_actuacion"
            value={actuacion}
            options={TIPOS_ACTUACION}
            onChange={setTipoActuacion}
          />
          {actuacion !== "" && (
            <RadioGroup
              legend={`Resultado del ${actuacion === "Operativo" ? "operativo" : "allanamiento"}`}
              name="resultado_actuacion"
              value={valorActuacion}
              options={RESULTADOS_ACTUACION}
              onChange={setResultadoActuacion}
              esActual={esResultadoActuacion}
            />
          )}
        </div>
      </section>

      <section className="panel xl:col-span-2">
        <h3 className="panel-title panel-title--cap mb-3">Personal que informa</h3>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,220px),1fr))] gap-3">
          <TextField
            label="Personal que informa"
            value={form.personal_informa}
            onChange={(value) => setCampo("personal_informa", value)}
          />
          <TextField
            label="Cargo del informante"
            value={form.cargo_informa}
            onChange={(value) => setCampo("cargo_informa", value)}
          />
          <Field label="Mini reseña">
            <textarea
              className={`${INPUT_CLASS} min-h-[80px] py-2`}
              value={form.mini_resena}
              onChange={(event) => setCampo("mini_resena", event.target.value)}
            />
          </Field>
        </div>
      </section>

      <div className="flex items-center justify-end gap-3 xl:col-span-2">
        <button
          type="submit"
          disabled={enviando}
          className="touch-target rounded-[10px] border border-accent bg-accent px-5 py-2 text-sm font-semibold text-[#04070F] transition-colors hover:bg-accent-bright disabled:cursor-not-allowed disabled:opacity-60"
        >
          {enviando ? textoEnviando : textoBoton}
        </button>
      </div>
    </form>
  );
}
