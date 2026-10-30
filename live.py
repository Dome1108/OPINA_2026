"""Combina el histórico con respuestas consultadas directamente por fechas."""
import pandas as pd

from core import reconcile


def merge_live(enrollment, historical_audit, fresh, start, end):
    lower = pd.Timestamp(start).tz_localize("America/Guayaquil").tz_convert("UTC")
    upper = (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize("America/Guayaquil").tz_convert("UTC")
    columns = ["response_id", "cedula_original", "estado_qp", "fecha"]
    # Sustituye estados antiguos y eliminaciones dentro del rango consultado.
    # Las fechas desconocidas se mantienen en revisión.
    outside = ~(historical_audit.fecha.ge(lower) & historical_audit.fecha.lt(upper))
    history = historical_audit.loc[outside, columns]
    responses = pd.concat([history, fresh[columns]], ignore_index=True).drop_duplicates("response_id", keep="last")
    return reconcile(enrollment, responses)
