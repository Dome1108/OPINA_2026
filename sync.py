"""Proceso independiente: nunca publica descargas incompletas."""
from datetime import datetime
import logging
import msvcrt
import tomllib
from zoneinfo import ZoneInfo

from connections import fetch_enrollment, fetch_questionpro
from core import parse_responses, reconcile
from storage import ROOT, save_snapshot


def main():
    directory = ROOT / "data"
    directory.mkdir(exist_ok=True)
    logging.basicConfig(filename=directory / "sync.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    with open(directory / "sync.lock", "a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            logging.info("Otra sincronización sigue activa; se omite este intento.")
            return
        try:
            logging.info("Iniciando sincronización completa.")
            with open(ROOT / ".streamlit" / "secrets.toml", "rb") as source:
                config = tomllib.load(source)
            qp = config["questionpro"]
            items = fetch_questionpro(qp, progress=lambda page, total: logging.info("QuestionPro: página %s/%s", page, total))
            responses = parse_responses(items, qp.get("question_code", "Q21"), qp.get("question_id", ""))
            frames = reconcile(fetch_enrollment(config["sql"]), responses)
            save_snapshot(frames, datetime.now(ZoneInfo("America/Guayaquil")))
            logging.info("Sincronización publicada: %s respuestas y %s estudiantes.", len(responses), len(frames[0]))
        except Exception as exc:
            # No registrar mensajes HTTP ni configuración: pueden incluir datos sensibles.
            logging.error("Sincronización fallida (%s). Se conserva la última instantánea.", type(exc).__name__)
            raise SystemExit(1)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == "__main__":
    main()
