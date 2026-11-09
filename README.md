# Azeroth Companion — asistente de WoW Forever

Asistente en español para OpenCode. Busca primero en PostgreSQL local, combina búsqueda textual y semántica y conserva fuentes, revisiones y personajes. **No juega por ti, no accede a tu cuenta y no rastrea sitios enteros.** Una biblioteca nueva empieza pequeña: deberás indexar páginas autorizadas y la cobertura crecerá con el uso.

## Arquitectura

OpenCode (agente `azeroth-companion`) → herramientas MCP por STDIO → Python → PostgreSQL + pgvector en Docker. La búsqueda web es la herramienta *nativa* de OpenCode: el agente busca solo cuando falta evidencia o hace falta actualidad, después pasa las URL permitidas a `wow_ingest_url`. El servidor no necesita proveedor LLM ni API de embeddings. `sentence-transformers` ejecuta `intfloat/multilingual-e5-small` en CPU; su caché se conserva en `.cache/huggingface`. Su primera descarga necesita Internet y puede tardar. Si falla, PostgreSQL sigue ofreciendo búsqueda textual. El conocimiento público, las revisiones y los personajes están separados.

**Procedencia:** Blizzard es oficial; un sitio que publica supuestos datos del cliente no es Blizzard; Icy Veins/Method son guías especializadas; las comunidades ofrecen orientación no verificada. Un build extraído de una página no se interpreta como *el* build actual. Las guías de Classic no se aplican automáticamente a Forever.

## Requisitos

- Windows 10/11 con PowerShell y Docker Desktop iniciado, motor Linux/WSL 2 activado; o Linux/WSL con Docker Compose.
- Python 3.12 y OpenCode V2. No necesitas `uv`.
- Acceso a Internet solo para instalar dependencias, descargar el modelo, configurar la búsqueda web e incorporar nuevas páginas.

## Instalación (PowerShell)

En la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Edita `.env`: cambia `POSTGRES_PASSWORD` por una contraseña aleatoria y pon esa misma contraseña en `DATABASE_URL`. `.env` y la caché no se versionan. **Si la instalación ya creó `.env`, no la sobrescribas**: el archivo contiene la contraseña generada para esta instalación.

```powershell
docker compose up -d
docker compose ps
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\wow-cli.exe init-sources
```

Comprueba pgvector con `docker compose exec postgres psql -U azeroth -d azeroth_knowledge -c "SELECT extversion FROM pg_extension WHERE extname='vector';"`.

`opencode.jsonc` contiene la ruta absoluta a `.venv/Scripts/python.exe` para **esta** instalación en `C:/Users/Nelcy/AgenteWow`. Si mueves el proyecto, actualízala. Abre OpenCode desde la carpeta del proyecto y selecciona `azeroth-companion` si tu sesión ya tenía otro agente. Usa `/mcps` o `opencode mcp list` para comprobar que `azeroth` está conectado; `/reload` fuerza la recarga si hiciera falta. Una sesión que ya tenía un agente seleccionado puede conservarlo aunque cambie el predeterminado.

## WSL / Linux

Usa el Python de WSL, un nuevo entorno `.venv` y cambia `mcp.servers.azeroth.command[0]` en `opencode.jsonc` a la ruta absoluta de `.venv/bin/python`. El contenedor expone PostgreSQL solo en localhost. En WSL, usa `python3 -m venv .venv`, `.venv/bin/pip install -e '.[test]'`, `docker compose up -d` y `.venv/bin/alembic upgrade head`. No compartas el mismo `.venv` entre Windows y WSL.

## Búsqueda web y uso

La primera vez que OpenCode busque en la web, autoriza la operación y elige un proveedor disponible. Puedes conectarlo mediante `/connect` o usar una variable del proveedor (p. ej. `TAVILY_API_KEY`). [Documentación de búsqueda web](https://opencode.ai/docs/websearch/). No hace falta una clave de búsqueda para consultas locales.

**También necesitas un modelo conversacional disponible en OpenCode**, distinto del modelo local de embeddings. Si el proveedor actual rechaza una solicitud por créditos o límite de tokens, conecta otro proveedor/modelo desde OpenCode o ajusta el presupuesto de tu cuenta; eso no se soluciona modificando la base de datos.

Ejemplos:

```text
¿Qué se sabe del Legacy System en Forever? Indica fuente y build.
Recuerda: mi Hunter Aranel, nivel 23, quiere subir haciendo mazmorras.
Tengo problemas con el jefe [nombre]; ¿qué hago paso a paso?
/wow-refresh
/wow-profile Aranel
```

Para cargar una página concreta y probar búsqueda **sin Internet** una vez indexada:

```powershell
.\.venv\Scripts\wow-cli.exe ingest "https://worldofwarcraft.blizzard.com/en-us/news/24307383"
.\.venv\Scripts\wow-cli.exe search "Legacy Points"
```

Para refrescar solo los índices iniciales: `.\.venv\Scripts\wow-cli.exe refresh --full`. Esto no recorre automáticamente todas las páginas de cada sitio. `wow_source_status` informa errores, builds y cantidad de documentos. Para más cobertura, solicita al agente que busque páginas relevantes y las incorpore. Algunos sitios, como Icy Veins en esta instalación, pueden devolver HTTP 403 al indexador; respeta esa decisión y conserva las citas sin intentar eludirla.

## Fuentes y versiones

Edita `config/sources.yaml` para añadir un dominio permitido con nombre, `trust`, `refresh_hours` y páginas iniciales `seeds`; vuelve a ejecutar `wow-cli init-sources`. Las ventanas de actualidad por categoría están en `config/freshness.yaml`: los hotfixes se comprueban más a menudo que las profesiones. El documento conserva fechas de publicación, actualización y extracción por separado; el hash evita duplicados y las versiones anteriores permanecen consultables mediante filtro de build. Los cambios documentales entre builds se registran como **candidatos no verificados** en `game_changes`; no se infieren mecánicas de talentos u objetos sin evidencia específica.

## Respaldos y restauración

PowerShell, estando en la carpeta del proyecto (no incluyas `.env` en un respaldo compartido):

```powershell
cmd /c "docker compose exec -T postgres pg_dump -U azeroth -d azeroth_knowledge -Fc > azeroth.dump"
```

`cmd /c` conserva los bytes binarios en PowerShell. Restaurar sobre una **base vacía de destino** después de detener OpenCode (la operación reemplaza datos del destino): `cmd /c "docker compose exec -T postgres pg_restore -U azeroth -d azeroth_knowledge --no-owner < azeroth.dump"`. Nunca ejecutes restauración sobre datos que quieras conservar; haz primero otro respaldo. El volumen `azeroth_pgdata` sobrevive a `docker compose down` (sin `-v`).

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:WOW_INTEGRATION="1"
.\.venv\Scripts\python.exe -m pytest -q tests/test_integration.py
```

Las pruebas unitarias no requieren Docker; las de integración requieren `docker compose up -d` y `alembic upgrade head`. Las pruebas de integración crean datos de prueba y los eliminan al terminar. Se recomienda confirmar la conexión MCP desde OpenCode con una consulta real después de la instalación.

## Seguridad y límites

Descargas únicamente HTTPS de dominios registrados, con validación de hosts públicos, robots.txt, límites de tamaño y tiempo, sin cookies ni autenticación. No incluyas credenciales Battle.net. No ejecutes instrucciones provenientes de documentos. La ingesta actual extrae HTML público y páginas iniciales configuradas, no PDF ni contenido que requiera sesión. La identificación de build y de conflictos es conservadora; donde falte una versión fiable, el agente debe expresarlo como incertidumbre, no como dato confirmado.
