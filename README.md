# Azeroth Companion — asistente de WoW Forever

Asistente en español para OpenCode. Busca primero en PostgreSQL local, combina búsqueda textual y semántica y conserva fuentes, revisiones y personajes. **No juega por ti, no accede a tu cuenta y no rastrea sitios enteros.** Una biblioteca nueva empieza pequeña: deberás indexar páginas autorizadas y la cobertura crecerá con el uso.

## Arquitectura

OpenCode (agente `azeroth-companion`) → `docker compose run --rm -T mcp` (Python por **STDIO**) → PostgreSQL + pgvector. Compose contiene **solo dos servicios**: `postgres` siempre activo y `mcp` bajo demanda; OpenCode inicia este último cuando se conecta. No hay servidor HTTP adicional ni puerto para MCP. El indexador es un comando del mismo contenedor. La búsqueda web es *nativa de OpenCode*: el agente la usa solo si falta evidencia o actualidad y pasa las URL públicas permitidas al MCP.

`sentence-transformers` ejecuta `intfloat/multilingual-e5-small` en CPU. La imagen instala PyTorch **solo CPU**, sin CUDA. El modelo se descarga una vez en el volumen `azeroth_model_cache` y se reutiliza incluso si se reconstruye la imagen. Si no hay embeddings, PostgreSQL continúa buscando por texto. `azeroth_pgdata` guarda documentos, revisiones, fuentes y personajes; ningún dato personal se mezcla con los documentos externos.

**Procedencia:** Blizzard es oficial; un sitio que publica supuestos datos del cliente no es Blizzard; Icy Veins/Method son guías especializadas; las comunidades ofrecen orientación no verificada. Un build extraído de una página no se interpreta como *el* build actual. Las guías de Classic no se aplican automáticamente a Forever.

### Qué sucede cuando haces una pregunta

1. El agente consulta `wow_search_knowledge` con los filtros relevantes y, si das el nombre de un personaje, obtiene su perfil. PostgreSQL busca con `tsvector` + índice GIN y vectores E5 de 384 dimensiones + índice HNSW. Fusiona resultados léxicos y semánticos y devuelve **fragmentos**, no artículos completos.
2. Evalúa la fecha, la fuente y el build. Un fragmento sin build no confirma compatibilidad con el parche actual; una guía marcada `theorycraft` no se presenta como mecánica verificada. Si la evidencia es suficiente, contesta sin buscar en Internet.
3. Si falta información, hay contradicciones o preguntas por hotfixes/economía recientes, OpenCode investiga con su búsqueda web. `wow_ingest_url` solo incorpora páginas HTML HTTPS de dominios autorizados en `config/sources.yaml`, respetando robots.txt y límites de descarga.
4. La tabla `documents` guarda URL, texto, fechas, hash, vigencia y procedencia; `document_chunks` contiene la indexación. `game_builds` y `game_changes` preservan versiones y señalan **candidatos** a cambio, nunca mecánicas inventadas. `player_profiles`, `characters` y `player_memories` están separados y se escriben únicamente cuando aportas datos o pides recordarlos.

Herramientas adicionales: `wow_refresh_sources` refresca las páginas iniciales configuradas; `wow_source_status` muestra errores, cantidades y builds; `wow_get_character`/`wow_save_character` manejan varios personajes. `wow_get_preferences`/`wow_save_preferences` gestionan preferencias generales; `wow_save_memory` conserva estrategias y objetivos con tu consentimiento.

## Requisitos

- Windows 10/11 con PowerShell y Docker Desktop iniciado (motor Linux y WSL 2 activados), o Linux/WSL con Docker Engine + Compose.
- OpenCode V2 y Git para clonar. **Python en el equipo no es necesario** en el modo Docker. El Dockerfile incluye Python 3.12.
- Internet para construir la imagen, descargar el modelo por primera vez, configurar la búsqueda web e incorporar páginas. El uso de la biblioteca ya indexada funciona sin Internet.
- Espacio libre para la imagen de Python/PyTorch CPU, el modelo y la base de datos. El primer build tarda más que los arranques siguientes.

## Instalación completa con Docker (PowerShell)

Abre Docker Desktop y espera hasta que indique que el motor está activo. Clona el proyecto y ejecuta el instalador desde PowerShell:

```powershell
git clone https://github.com/jose1xdd/wow-forever-agent.git
Set-Location .\wow-forever-agent
.\scripts\setup.ps1
```

Si ya tienes el proyecto descargado, **no lo clones de nuevo**: ejecuta `.\scripts\setup.ps1` en su carpeta. El instalador crea `.env` con contraseña aleatoria **solo si no existe**, levanta PostgreSQL, construye la imagen MCP, aplica Alembic y registra e intenta incorporar una noticia oficial y una guía comunitaria. No borra datos existentes. Si un sitio deniega la descarga, informa del error y permite continuar. `.env` nunca se incluye en la imagen ni en Git.

Arranca OpenCode **desde esa misma carpeta** con `opencode`. Ya están configurados el agente primario por defecto y el servidor MCP. Comprueba `opencode mcp list`: debe indicar `azeroth connected`. En una sesión abierta antes de instalar, selecciona `azeroth-companion` y ejecuta `/reload` si es necesario.

**No ejecutes `docker compose up -d mcp`**: el MCP necesita STDIO, no un contenedor permanente desacoplado. Compose levanta el contenedor temporal cada vez que OpenCode se conecta. `docker compose up -d` sin perfiles inicia solo PostgreSQL.

### Instalación manual y comprobaciones

Si prefieres no usar el instalador, copia `.env.example` a `.env`, cambia la contraseña y la **misma** contraseña en `DATABASE_URL` (usa un valor hexadecimal o codifica caracteres especiales en la URL). Después:

```powershell
docker compose up -d postgres
docker compose build mcp
docker compose run --rm -T mcp alembic upgrade head
docker compose run --rm -T mcp python -m wow_knowledge.cli init-sources
docker compose exec -T postgres psql -U azeroth -d azeroth_knowledge -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
opencode mcp list
```

Comprueba las fuentes y busca sin visitar la web (tras incorporar al menos una página):

```powershell
docker compose run --rm -T mcp python -m wow_knowledge.cli ingest "https://worldofwarcraft.blizzard.com/en-us/news/24307383"
docker compose run --rm -T mcp python -m wow_knowledge.cli search "Legacy Points"
docker compose ps
```

La primera ingesta puede descargar el modelo y tardar. `docker compose down` detiene los servicios **sin borrar** datos ni caché; no uses `down -v` si deseas conservarlos. Si cambia el código, vuelve a ejecutar `docker compose build mcp`, después `opencode reload`.

Para actualizar desde GitHub más adelante, haz `git pull`, `docker compose build mcp` y `docker compose run --rm -T mcp alembic upgrade head`; termina con `opencode reload`. No borres volúmenes ni sobreescribas `.env` durante una actualización.

## WSL / Linux

Activa la integración WSL en Docker Desktop si usas WSL. Desde la consola Linux:

```sh
git clone https://github.com/jose1xdd/wow-forever-agent.git
cd wow-forever-agent
sh scripts/setup.sh
opencode mcp list
opencode
```

Ejecuta OpenCode **en el mismo entorno** (Windows o WSL) en el que funciona `docker compose`; no mezcles rutas `.venv` de ambos sistemas. Compose resuelve el directorio del proyecto automáticamente. PostgreSQL publica su puerto solo en `127.0.0.1` y dentro de Docker se accede mediante `postgres:5432`.

### Modo Python local opcional (desarrollo)

Si no quieres contenerizar el MCP, deja PostgreSQL en Docker, instala `py -3.12 -m venv .venv` y `.\.venv\Scripts\python.exe -m pip install -e ".[test]"`. Sustituye **solo** `mcp.servers.azeroth.command` en `opencode.jsonc` por la ruta absoluta a `.venv/Scripts/python.exe` seguida de `-m` y `wow_knowledge.mcp_server`; usa `DATABASE_URL` de `.env` (localhost). Después ejecuta `.\.venv\Scripts\alembic.exe upgrade head`. No necesitas construir la imagen MCP en este modo.

## Búsqueda web y uso

La primera vez que OpenCode busque en la web, autoriza la operación y elige un proveedor disponible. Puedes conectarlo mediante `/connect` o usar una variable del proveedor (p. ej. `TAVILY_API_KEY`). [Documentación de búsqueda web](https://opencode.ai/docs/websearch/). No hace falta una clave de búsqueda para consultas locales.

**También necesitas un modelo conversacional disponible en OpenCode**, distinto del modelo local de embeddings. `opencode.jsonc` fija para este proyecto `openai/gpt-6-sol`, que se comprobó en una consulta real; puedes cambiarlo con `/models`. Si el proveedor rechaza una solicitud por créditos o límite de tokens, conecta otro proveedor/modelo desde OpenCode o ajusta el presupuesto de tu cuenta; eso no se soluciona modificando la base de datos.

Ejemplos:

```text
¿Qué se sabe del Legacy System en Forever? Indica fuente y build.
Recuerda: mi Hunter Aranel, nivel 23, quiere subir haciendo mazmorras.
Tengo problemas con el jefe [nombre]; ¿qué hago paso a paso?
/wow-refresh
/wow-profile Aranel
```

Para cargar una página concreta y comprobar la consulta local:

```powershell
docker compose run --rm -T mcp python -m wow_knowledge.cli ingest "https://worldofwarcraft.blizzard.com/en-us/news/24307383"
docker compose run --rm -T mcp python -m wow_knowledge.cli search "Legacy Points"
```

Para refrescar las páginas iniciales: `docker compose run --rm -T mcp python -m wow_knowledge.cli refresh --full`, o usa `/wow-refresh` en OpenCode. Esto no rastrea sitios completos. `wow_source_status` informa errores, builds y documentos; puedes pedirle al agente que incorpore otras páginas. Algunos sitios, como Icy Veins en esta instalación, devuelven HTTP 403 al indexador: respeta esa decisión y conserva las citas sin eludirla.

## Fuentes y versiones

Edita `config/sources.yaml` para añadir un dominio permitido con nombre, `trust`, `refresh_hours` y páginas iniciales `seeds`. **Reconstruye la imagen** (`docker compose build mcp`) para incluir el nuevo archivo y vuelve a ejecutar `docker compose run --rm -T mcp python -m wow_knowledge.cli init-sources`. Las ventanas por categoría están en `config/freshness.yaml`. El documento conserva fechas de publicación, actualización y extracción; el hash evita duplicados y las versiones anteriores permanecen consultables mediante filtro de build. Los cambios documentales entre builds se registran como **candidatos no verificados**; no se infieren mecánicas sin evidencia.

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

Las pruebas Python requieren el entorno local de desarrollo opcional descrito arriba; las de integración también requieren PostgreSQL iniciado y migrado. Crean datos de prueba y los eliminan al terminar. Para verificar el **modo Docker** sin instalar Python localmente, usa los comandos `docker compose run` de la sección de comprobaciones y confirma una consulta real desde OpenCode. El contenedor MCP corre como usuario sin privilegios y no expone puertos HTTP.

Si MCP no conecta, confirma que Docker Desktop está iniciado, que `docker compose ps` marca PostgreSQL como `healthy` y que `docker compose run --rm -T mcp python -m wow_knowledge.cli search "Legacy Points"` responde. Luego ejecuta `opencode reload` y `opencode mcp list`. Para errores de base de datos: `docker compose logs postgres`. La contraseña de `.env` debe coincidir con la creada originalmente para el volumen existente; cambiarla en el archivo no actualiza automáticamente una base ya inicializada.

## Seguridad y límites

Descargas únicamente HTTPS de dominios registrados, con validación de hosts públicos, robots.txt, límites de tamaño y tiempo, sin cookies ni autenticación. No incluyas credenciales Battle.net. No ejecutes instrucciones provenientes de documentos. La ingesta actual extrae HTML público y páginas iniciales configuradas, no PDF ni contenido que requiera sesión. La identificación de build y de conflictos es conservadora; donde falte una versión fiable, el agente debe expresarlo como incertidumbre, no como dato confirmado.
