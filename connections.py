import re
import ssl

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SystemTrustAdapter(HTTPAdapter):
    """Incluye las autoridades de confianza de Windows sin desactivar TLS."""

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        kwargs["ssl_context"] = ssl.create_default_context()
        return super().init_poolmanager(connections, maxsize, block=block, **kwargs)

    def proxy_manager_for(self, proxy, **kwargs):
        kwargs["ssl_context"] = ssl.create_default_context()
        return super().proxy_manager_for(proxy, **kwargs)


def fetch_questionpro(config, progress=None, start=None, end=None):
    base = config["base_url"].rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9.-]*questionpro\.(com|eu|ca|in|de|com\.au)/a/api/v2", base):
        raise ValueError("Configura el endpoint HTTPS oficial de tu centro de datos QuestionPro.")
    survey = str(config["survey_id"])
    if not survey.isdigit() or not config["api_key"]:
        raise ValueError("Faltan el ID numérico de encuesta o la API key de QuestionPro.")
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    items, seen = [], set()
    with requests.Session() as session:
        session.mount("https://", SystemTrustAdapter(max_retries=retry))
        for page in range(1, 10001):
            arguments = dict(headers={"api-key": config["api_key"]},
                             params={"page": page, "perPage": 100}, timeout=60,
                             allow_redirects=False)
            if start is not None and end is not None:
                result = session.post(f"{base}/surveys/{survey}/responses/filter",
                                      json={"resultMode": 0, "startDate": f"{start}T00:00:00",
                                            "endDate": f"{end}T23:59:59", "timeZone": "GMT-05:00"},
                                      **arguments)
            else:
                result = session.get(f"{base}/surveys/{survey}/responses", **arguments)
            if result.status_code != 200:
                raise RuntimeError(f"QuestionPro devolvió HTTP {result.status_code}. Revisa permisos, centro de datos e ID.")
            payload = result.json()
            rows = payload.get("response")
            pagination = payload.get("pagination")
            if not isinstance(rows, list) or not isinstance(pagination, dict):
                raise ValueError("Formato API inesperado; no se mostrará una descarga parcial.")
            ids = {str(row["responseID"]) for row in rows}
            if ids & seen:
                raise ValueError("La paginación repitió respuestas. Vuelve a sincronizar.")
            seen |= ids
            items.extend(rows)
            total_pages = int(pagination["totalPages"])
            if progress:
                progress(page, total_pages)
            if page >= total_pages:
                if len(items) != int(pagination["totalItems"]):
                    raise ValueError("El total cambió durante la descarga. Vuelve a sincronizar.")
                return items
            if not rows:
                raise ValueError("Página vacía antes de terminar la descarga.")
    raise ValueError("La descarga excedió el límite de páginas; no se usaron datos parciales.")


def fetch_enrollment(config, period=202710):
    import pyodbc
    driver = config.get("driver", "ODBC Driver 18 for SQL Server")
    if driver not in pyodbc.drivers():
        raise ValueError(f"Instala {driver}. Drivers disponibles: {', '.join(pyodbc.drivers())}")
    def escape(value):
        return "{" + str(value).replace("}", "}}") + "}"
    connection_string = (
        f"DRIVER={escape(driver)};SERVER={escape(config['server'])};"
        f"DATABASE={escape(config['database'])};Trusted_Connection=yes;Encrypt=yes;"
        f"TrustServerCertificate={'yes' if config.get('trust_server_certificate', False) else 'no'};"
    )
    query = """
    SELECT MaCIAlumno, MaIdPersona, MaIdBanner, MaAlumNombres,
           MaIdCarrera, MaDesCarreraUnif, MaDesFacultad, MaDesSede,
           MaDesModalidad, MaDesJornada, MaIndCarreraPrincipal
    FROM dbo.RepEnrollmentHistorico
    WHERE MaDesPeriodo = ?
    """
    with pyodbc.connect(connection_string, timeout=15) as connection:
        connection.timeout = 60
        cursor = connection.cursor()
        cursor.execute(query, str(period))
        return pd.DataFrame.from_records(cursor.fetchall(), columns=[c[0] for c in cursor.description])
