from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from core import DIMENSIONS, lookup_response, normalize, parse_responses
from connections import fetch_questionpro, fetch_enrollment
from live import merge_live
from storage import read_snapshot, DATABASE

st.set_page_config(page_title="OPINA | Participación", page_icon="📊", layout="wide")
st.markdown("""<style>
.stApp {background:#f6f7fa} h1,h2,h3 {color:#69132d}
[data-testid="stMetric"] {background:white;padding:18px;border-radius:12px;border-top:3px solid #8b193e}
</style>""", unsafe_allow_html=True)
st.title("OPINA · Participación estudiantil")
st.caption("Período 202710 · Primera respuesta completada por cédula · Enrollment institucional")

@st.cache_data(show_spinner=False, max_entries=2)
def load(version):
    return read_snapshot()


@st.cache_data(ttl=30, show_spinner=False)
def live_recent(start, end):
    qp = st.secrets["questionpro"]
    return parse_responses(fetch_questionpro(qp, start=start, end=end),
                           qp.get("question_code", "Q21"), qp.get("question_id", ""))


@st.cache_data(ttl=60, show_spinner=False)
def current_enrollment():
    return fetch_enrollment(st.secrets["sql"])


@st.fragment(run_every="30s")
def dashboard():
    try:
        students, audit, missing, repeated, updated = load(DATABASE.stat().st_mtime_ns)
    except FileNotFoundError:
        st.info("Preparando los datos por primera vez. La consulta estará disponible al terminar la sincronización inicial.")
        return
    except Exception as exc:
        st.error("No se pudo leer la última actualización guardada. Revisa el proceso de sincronización.")
        return
    historical_audit = audit.copy()
    now = datetime.now(ZoneInfo("America/Guayaquil"))
    st.caption(f"Histórico base: {updated:%d/%m/%Y %H:%M:%S} · Ecuador")
    try:
        fresh = live_recent((updated.date() - timedelta(days=1)).isoformat(), now.date().isoformat())
        students, audit, missing, repeated = merge_live(current_enrollment(), audit, fresh,
                                                       updated.date() - timedelta(days=1), now.date())
        st.caption("Respuestas recientes consultadas automáticamente en QuestionPro cada 30 segundos. "
                   "La consulta por cédula comprueba directamente el rango que selecciones.")
    except Exception:
        st.warning("No se pudo consultar QuestionPro o SQL en vivo. Los indicadores muestran la copia guardada; "
                   "no confirman el estado actual. Puedes intentar la consulta directa por cédula.")
    if students.empty:
        st.warning("El período no devolvió estudiantes con cédula de 10 dígitos. Revisa las incidencias.")
    today = datetime.now(ZoneInfo("America/Guayaquil")).date()
    available_dates = audit.fecha.dropna().dt.tz_convert("America/Guayaquil")
    date_columns = st.columns(2)
    participation_start = date_columns[0].date_input(
        "Participación: fecha inicial", key="participation_start",
        value=available_dates.min().date() if len(available_dates) else today)
    participation_end = date_columns[1].date_input(
        "Participación: fecha final", key="participation_end",
        value=max(available_dates.max().date(), today) if len(available_dates) else today)
    valid_range = participation_start <= participation_end
    if not valid_range:
        st.error("Participación: la fecha inicial debe ser anterior o igual a la final.")
    st.caption("Fechas inclusivas de Ecuador. Indicadores, gráfico y tablas cuentan la primera respuesta válida "
               "dentro del rango. El total de estudiantes no cambia por fecha; pendientes significa sin primera "
               "respuesta válida en ese rango. Los duplicados posteriores no vuelven a contar.")
    filtered = students.copy()
    lower = pd.Timestamp(participation_start).tz_localize("America/Guayaquil").tz_convert("UTC")
    upper = (pd.Timestamp(participation_end) + pd.Timedelta(days=1)).tz_localize("America/Guayaquil").tz_convert("UTC")
    filtered["Respondió"] = filtered["Respondió"] & filtered.fecha.ge(lower) & filtered.fecha.lt(upper) & valid_range
    filtered["Estado"] = filtered["Respondió"].map({True: "Completó", False: "Pendiente"})
    columns = st.columns(5)
    for column, (label, field) in zip(columns, DIMENSIONS.items()):
        values = sorted(students[field].fillna("Sin dato").astype(str).unique())
        selected = column.multiselect(label, values, key=field)
        if selected:
            filtered = filtered[filtered[field].fillna("Sin dato").astype(str).isin(selected)]
    total, done = len(filtered), int(filtered["Respondió"].sum())
    if not valid_range:
        st.info("Corrige el rango para calcular la participación.")
    metrics = st.columns(4)
    for column, label, value in zip(metrics,
                                    ["Estudiantes", "Completaron", "Pendientes", "Participación"],
                                    [total, done if valid_range else "—", total - done if valid_range else "—",
                                     (f"{done / total:.1%}" if total else "0%") if valid_range else "—"]):
        column.metric(label, value)
    overview, search, incidents = st.tabs(["Participación", "Consulta por cédula", "Auditoría"])
    with overview:
        if not valid_range:
            st.warning("No se calculan gráficos ni tablas con un rango inválido.")
        render_participation(filtered, valid_range)
    with search:
        render_search(students, historical_audit)
    with incidents:
        render_audit(audit, missing, repeated)


def render_participation(filtered, valid_range):
        if not valid_range:
            return
        label = st.selectbox("Agrupar participación por", list(DIMENSIONS))
        field = DIMENSIONS[label]
        grouped = filtered.groupby(field, dropna=False)["Respondió"].agg(
            Estudiantes="size", Completaron="sum").reset_index()
        grouped["Pendientes"] = grouped.Estudiantes - grouped.Completaron
        grouped["Participación %"] = (grouped.Completaron / grouped.Estudiantes * 100).round(1)
        st.bar_chart(grouped.set_index(field)[["Completaron", "Pendientes"]], color=["#8b193e", "#cbd2df"])
        st.dataframe(grouped, hide_index=True, use_container_width=True)
        show = st.radio("Ver estudiantes", ["Todos", "Completó", "Pendiente"], horizontal=True)
        detail = filtered if show == "Todos" else filtered[filtered.Estado.eq(show)]
        st.dataframe(detail.drop(columns=["Respondió", "MaCIAlumno"]), hide_index=True, use_container_width=True)


def render_search(students, audit):
        st.subheader("Verificar encuesta y enrollment")
        today = datetime.now(ZoneInfo("America/Guayaquil")).date()
        date_columns = st.columns(2)
        start = date_columns[0].date_input("Fecha inicial de QuestionPro", value=today.replace(day=1))
        end = date_columns[1].date_input("Fecha final de QuestionPro", value=today)
        cedula = st.text_input("Cédula exacta", max_chars=10, placeholder="10 dígitos")
        st.caption("Fechas inclusivas de Ecuador. Pulsa Consultar en vivo para leer QuestionPro y SQL Server ahora. "
                   "Un rango corto evita descargar respuestas de años anteriores.")
        submitted = st.button("Consultar en vivo", type="primary")
        query_key = (normalize(cedula), str(start), str(end))
        if submitted and not cedula:
            st.warning("Ingresa la cédula que deseas consultar.")
        if submitted and cedula:
            if start > end:
                st.error("La fecha inicial debe ser anterior o igual a la final.")
            elif len(normalize(cedula)) != 10 or not normalize(cedula).isascii() or not normalize(cedula).isdigit():
                st.warning("Ingresa una cédula de 10 dígitos.")
            else:
                st.session_state.pop("live_lookup", None)
                try:
                    qp = st.secrets["questionpro"]
                    with st.spinner("Consultando QuestionPro y enrollment en vivo…"):
                        fresh = parse_responses(fetch_questionpro(qp, start=start.isoformat(), end=end.isoformat()),
                                                qp.get("question_code", "Q21"), qp.get("question_id", ""))
                        live_students, live_audit, _, _ = merge_live(fetch_enrollment(st.secrets["sql"]), audit, fresh, start, end)
                        result = lookup_response(live_students, live_audit, cedula, start, end)
                        st.session_state.live_lookup = (query_key, result, datetime.now(ZoneInfo("America/Guayaquil")))
                except Exception as exc:
                    st.error(f"No se pudo verificar en vivo ({type(exc).__name__}). No se confirma que haya respondido ni que esté pendiente. Vuelve a intentarlo.")
        stored = st.session_state.get("live_lookup")
        if stored and stored[0] == query_key:
                _, result, checked = stored
                st.caption(f"Consulta realizada para la cédula {normalize(cedula)} · "
                           f"{start:%d/%m/%Y} al {end:%d/%m/%Y} · Verificada en vivo: {checked:%d/%m/%Y %H:%M:%S}. "
                           "Pulsa Consultar en vivo para comprobar nuevamente.")
                st.write("**1. ¿Completó la encuesta en las fechas seleccionadas?**")
                if result["answered"]:
                    st.success("Sí. Hay una respuesta completada en QuestionPro en ese rango.")
                elif result["unknown_count"]:
                    st.warning("No se encontró una completada con fecha dentro del rango. Hay respuestas sin fecha interpretable: requiere revisión.")
                else:
                    st.warning("QuestionPro no devolvió una respuesta completada para esta cédula en el rango consultado en vivo.")
                st.write("**2. ¿La cédula consta en el enrollment 202710?**")
                if result["enrolled"]:
                    st.success("Sí. La cédula está registrada en el enrollment 202710.")
                    st.dataframe(result["student"].drop(columns=["Respondió", "MaCIAlumno", "Estado", "response_id", "fecha"]), hide_index=True)
                else:
                    st.warning("No. La cédula no consta en el enrollment utilizable del período 202710.")
                st.write("**Resultado de validación**")
                if result["accepted"]:
                    st.success("Válida: primera encuesta completada dentro del rango y cédula en el enrollment.")
                elif result["unknown_date"]:
                    st.warning("Requiere revisión de fechas antes de decidir cuál fue la primera respuesta.")
                else:
                    st.warning("No válida para este rango: falta una primera respuesta completada dentro del rango o la coincidencia en enrollment.")
                if result["first"] is not None:
                    first_date = result["first"].fecha.tz_convert("America/Guayaquil")
                    st.info(f"Primera respuesta completada registrada: {first_date:%d/%m/%Y %H:%M:%S} (Ecuador). "
                            "Las respuestas posteriores no vuelven a contar, aunque sean de otra fecha.")
                st.caption("Los duplicados se comprueban con el histórico guardado y el rango recién consultado. "
                           "Cambios o completados de respuestas anteriores fuera de ese rango requieren renovar el histórico.")
                st.write("Respuestas de QuestionPro en las fechas seleccionadas")
                display = result["responses"].copy()
                display["fecha"] = display.fecha.dt.tz_convert("America/Guayaquil")
                st.dataframe(display, hide_index=True)


def render_audit(audit, missing, repeated):
        st.caption("Estas cifras corresponden a toda la encuesta configurada, sin filtros de carrera o fecha.")
        st.dataframe(audit.resultado.value_counts().rename_axis("Resultado").reset_index(name="Respuestas"),
                     hide_index=True)
        st.dataframe(audit, hide_index=True, use_container_width=True)
        with st.expander(f"Enrollment con cédulas no utilizables: {len(missing)} filas"):
            st.dataframe(missing, hide_index=True)
        with st.expander(f"Enrollment con varias filas por cédula: {len(repeated)} filas"):
            st.caption("Se usa la carrera principal; en empates se elige el menor ID de carrera. Requiere revisión si hay varios titulares.")
            st.dataframe(repeated, hide_index=True)
        st.info("Una coincidencia comprueba pertenencia al enrollment. No autentica la identidad del encuestado. "
                "La comprobación actual valida formato y coincidencia, no el dígito verificador de la cédula.")


dashboard()
