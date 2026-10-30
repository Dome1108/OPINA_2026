# OPINA 2026

Dashboard de Streamlit para verificar encuestas de QuestionPro y cruzar cédulas con el enrollment de SQL Server del período **202710** (`MaDesPeriodo`; ID interno 238).

## Replicar en otra computadora

Necesitas **Windows, Python 3.11 de 64 bits, Git, Microsoft ODBC Driver 17 o 18 for SQL Server**, acceso a la red institucional/VPN y permisos Windows de lectura en `SNBI03`, base `DwhOperacional`, tabla `dbo.RepEnrollmentHistorico`.

```powershell
git clone https://github.com/Dome1108/OPINA_2026.git
cd OPINA_2026
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Completa `.streamlit/secrets.toml` con la API key, comprueba el ID de encuesta y el código de pregunta Q21. Ajusta `driver` al controlador instalado. El proceso hereda tu usuario Windows; clonar el proyecto no concede permisos en SQL Server.

SQL utiliza `Encrypt=yes`. La plantilla verifica el certificado (`trust_server_certificate = false`). Si falla por una autoridad no confiable, solicita el certificado a TI. En el equipo original se necesitó `trust_server_certificate = true` para el certificado institucional: conserva el cifrado pero omite comprobar la identidad del servidor.

Genera el histórico inicial:

```powershell
.\.venv\Scripts\python.exe sync.py
```

La primera descarga completa puede tardar unos diez minutos con 220 páginas. El progreso queda en `data/sync.log`. Espera hasta ver `Sincronización publicada` antes de abrir el dashboard por primera vez.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Abre http://localhost:8501. La base local se regenera desde las fuentes; no se incluye en Git porque contiene nombres, cédulas y respuestas. La API key tampoco se incluye: colócala de forma privada en cada equipo. El entorno `.venv` se crea con los comandos anteriores.

## Consulta y actualización

- **Consulta por cédula:** selecciona fechas y pulsa **Consultar en vivo**. Lee directamente QuestionPro y SQL Server y muestra la hora de comprobación. Se informa por separado si completó la encuesta y si pertenece al enrollment. Los errores de conexión no se convierten en resultados negativos.
- **Indicadores:** cada 30 segundos consultan respuestas desde el día anterior al histórico base hasta hoy. Enrollment tiene caché de 60 segundos. Los filtros de fecha recalculan indicadores, gráfico y tablas manteniendo el denominador de estudiantes. Fechas inclusivas de Ecuador.
- **Histórico:** SQLite conserva una instantánea completa. `sync.py` descarga todas las páginas y publica en una transacción; si falla, mantiene la anterior. Un bloqueo local impide sincronizaciones simultáneas.
- **Límite:** cambios, eliminaciones o respuestas iniciadas antes de la ventana y completadas después pueden requerir consultar ese rango o renovar el histórico. Los indicadores no son una réplica instantánea completa de todos los años. La API puede tener latencia propia y los rangos amplios necesitan más páginas.

QuestionPro utiliza API key, no login automatizado del navegador. HTTPS incorpora las autoridades de confianza de Windows sin desactivar la verificación TLS.

Referencias: [respuestas](https://www.questionpro.com/api/get-responses.html), [consulta por fechas](https://www.questionpro.com/api/create-response-filter.html), [autenticación](https://www.questionpro.com/api/authentication.html).

## Validación

Solo `Completed` cuenta. Se mantienen las cédulas como texto y sus ceros iniciales; se eliminan espacios, puntos y guiones. Se exige formato de 10 dígitos y coincidencia exacta en enrollment; no se valida el dígito verificador ni la identidad del encuestado.

Cuenta la primera respuesta completada conocida por cédula. Las posteriores no suman aunque cambie la fecha. La consulta combina el histórico base con el rango recién leído; cambios anteriores fuera del rango necesitan renovar el histórico. Fechas desconocidas requieren revisión.

Enrollment se consulta sin TOP 1000. Una persona con varias filas cuenta una vez, priorizando carrera principal y luego menor ID de carrera. Auditoría muestra las incidencias. No se aplican filtros adicionales por pago, retiro o graduación. El dashboard excluye duplicados pero no bloquea nuevos envíos en QuestionPro; eso requiere acceso individual configurado allí.

## Automatización del histórico

`install-sync.ps1` prepara `OPINA-Sincronizacion` cada 15 minutos, con sesión Windows iniciada, privilegios normales y sin instancias superpuestas. Prefiere Python de `.venv`.

**Cylance Script Control bloqueó el instalador en el equipo original y la tarea no quedó instalada.** Solicita a TI el mecanismo autorizado sin desactivar la protección. Para registro manual en el Programador de tareas: programa `.venv\Scripts\pythonw.exe` con su ruta absoluta, argumento ruta absoluta a `sync.py` entre comillas, iniciar en la carpeta del proyecto, repetir cada 15 minutos y no iniciar una nueva instancia si otra sigue activa. El equipo debe estar encendido, con sesión iniciada y acceso a la red institucional.

La clave se lee del archivo local; nunca se coloca en los argumentos de la tarea. La consulta en vivo no necesita esa tarea mientras el dashboard está abierto.

## Estructura y pruebas

| Archivo | Función |
|---|---|
| `app.py` | Interfaz, filtros y consulta en vivo |
| `connections.py` | SQL Server y QuestionPro |
| `core.py` | Normalización y validación |
| `live.py` | Combina histórico con consultas recientes |
| `storage.py` | Instantáneas SQLite |
| `sync.py` | Descarga completa independiente |
| `install-sync.ps1` | Registro opcional de tarea Windows |
| `.streamlit/secrets.toml.example` | Plantilla sin credenciales |
| `tests/` | Pruebas con datos sintéticos |

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

No publiques `secrets.toml`, `data/`, bases SQLite o entornos virtuales. No expongas el puerto a Internet sin autenticación y autorización institucional. Cada computadora necesita sus propios permisos Windows y conectividad.
