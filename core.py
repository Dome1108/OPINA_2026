"""Cruce por cédula: una primera respuesta completada por campaña."""
import re
import pandas as pd
from dateutil import parser

DIMENSIONS = {
    "Carrera": "MaDesCarreraUnif", "Facultad": "MaDesFacultad",
    "Sede": "MaDesSede", "Modalidad": "MaDesModalidad", "Jornada": "MaDesJornada",
}


def normalize(value):
    if value is None or pd.isna(value):
        return ""
    # No convertir a número ni completar ceros: podría crear coincidencias falsas.
    return re.sub(r"[\s.-]", "", str(value).strip())


def timestamp(response):
    raw = response.get("utctimestamp")
    if raw is not None:
        try:
            number = float(raw)
            # No aceptar valores de ejemplo ni segundos fuera de rango moderno.
            seconds = number / 1000 if number > 100_000_000_000 else number
            if 946684800 <= seconds <= 4102444800:
                return pd.to_datetime(seconds, unit="s", utc=True)
        except (ValueError, TypeError, OverflowError):
            pass
    try:
        offsets = {"UTC": 0, "GMT": 0, "PDT": -25200, "PST": -28800,
                   "EDT": -14400, "EST": -18000, "ECT": -18000}
        result = parser.parse(str(response.get("timestamp", "")), tzinfos=offsets)
        # Una fecha sin zona no permite decidir con seguridad cuál fue primera.
        return pd.Timestamp(result).tz_convert("UTC") if result.tzinfo else pd.NaT
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def parse_responses(items, question_code="Q21", question_id=""):
    rows = []
    for item in items:
        answers = []
        for question in item.get("responseSet", []):
            matches = (str(question.get("questionID")) == str(question_id)) if question_id else (
                question.get("questionCode") == question_code)
            if matches:
                for answer in question.get("answerValues", []):
                    text = (answer.get("value") or {}).get("text", "")
                    if text is not None and str(text).strip():
                        answers.append(str(text))
        rows.append({"response_id": str(item["responseID"]),
                     "cedula_original": answers[0] if len(answers) == 1 else "",
                     "estado_qp": str(item.get("responseStatus", "")),
                     "fecha": timestamp(item)})
    frame = pd.DataFrame(rows, columns=["response_id", "cedula_original", "estado_qp", "fecha"])
    frame["fecha"] = pd.to_datetime(frame["fecha"], utc=True)
    return frame.drop_duplicates("response_id")


def reconcile(enrollment, responses):
    enrollment = enrollment.copy()
    enrollment["cedula"] = enrollment.MaCIAlumno.map(normalize)
    missing = enrollment[~enrollment.cedula.str.fullmatch(r"[0-9]{10}")].copy()
    enrollment = enrollment[enrollment.cedula.str.fullmatch(r"[0-9]{10}")].copy()
    # Para múltiples carreras se elige la principal; empates, por ID de carrera.
    enrollment["_principal"] = enrollment.MaIndCarreraPrincipal.astype(str).str.upper().isin(
        ["1", "TRUE", "S", "SI", "SÍ", "Y", "YES"])
    enrollment = enrollment.sort_values(["_principal", "MaIdCarrera"], ascending=[False, True])
    repeated = enrollment[enrollment.duplicated("cedula", keep=False)].copy()
    enrollment = enrollment.drop_duplicates("cedula").drop(columns="_principal")
    audit = responses.copy()
    audit["cedula"] = audit.cedula_original.map(normalize)
    audit["resultado"] = "No completada"
    complete = audit.estado_qp.str.casefold().eq("completed")
    valid_format = audit.cedula.str.fullmatch(r"[0-9]{10}")
    audit.loc[complete & ~valid_format, "resultado"] = "Cédula vacía o formato incorrecto"
    audit.loc[complete & valid_format, "resultado"] = "Fuera del enrollment"
    candidates = complete & valid_format & audit.cedula.isin(enrollment.cedula)
    audit.loc[candidates, "resultado"] = "Válida"
    # Si falta una fecha, no inventar el orden de las respuestas de esa cédula.
    unknown = audit.loc[candidates & audit.fecha.isna(), "cedula"]
    audit.loc[candidates & audit.cedula.isin(unknown), "resultado"] = "Revisar fecha"
    ordered = audit[audit.resultado.eq("Válida")].sort_values(["fecha", "response_id"])
    duplicates = ordered[ordered.duplicated("cedula")].index
    audit.loc[duplicates, "resultado"] = "Duplicada: no válida"
    accepted = audit[audit.resultado.eq("Válida")][["cedula", "response_id", "fecha"]]
    students = enrollment.merge(accepted, on="cedula", how="left", validate="one_to_one")
    students["Respondió"] = students.response_id.notna()
    students["Estado"] = students["Respondió"].map({True: "Completó", False: "Pendiente"})
    return students, audit, missing, repeated


def lookup_response(students, audit, cedula, start, end):
    """Consulta QP independientemente del enrollment; días inclusivos de Ecuador."""
    cedula = normalize(cedula)
    lower = pd.Timestamp(start).tz_localize("America/Guayaquil").tz_convert("UTC")
    upper = (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize("America/Guayaquil").tz_convert("UTC")
    if lower >= upper:
        raise ValueError("La fecha inicial debe ser anterior o igual a la final.")
    history = audit[audit.cedula.eq(cedula)].copy()
    completed = history[history.estado_qp.str.casefold().eq("completed")].sort_values(
        ["fecha", "response_id"])
    in_range = history.fecha.ge(lower) & history.fecha.lt(upper)
    selected = history[in_range].copy()
    answered = selected.estado_qp.str.casefold().eq("completed").any()
    unknown = completed.fecha.isna().any()
    first = completed.iloc[0] if len(completed) and not unknown else None
    first_in_range = first is not None and lower <= first.fecha < upper
    enrollment = students[students.cedula.eq(cedula)]
    return {"answered": bool(answered), "enrolled": not enrollment.empty,
            "first": first, "unknown_date": bool(unknown),
            "accepted": bool(first_in_range and not enrollment.empty),
            "responses": selected, "student": enrollment,
            "unknown_count": int(history.fecha.isna().sum())}
