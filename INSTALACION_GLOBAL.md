# Usar Azeroth Companion desde cualquier proyecto de OpenCode

Esta guía instala **el agente y su MCP para tu usuario**, sin hacerlos predeterminados en todos los proyectos. Puedes abrir OpenCode en otra carpeta y seleccionar `azeroth-companion`: seguirá consultando **la misma** base PostgreSQL de esta instalación. Las Skills de arquitectura en `.opencode/skills/` siguen siendo específicas de este repositorio.

> Este procedimiento configura **OpenCode V2 en la máquina donde se ejecuta**. La configuración global no se sube a GitHub. No copies `.env`, contraseñas ni la base de datos a otros proyectos.

## 1. Prepara la instalación principal

Necesitas Git, OpenCode V2, Docker Engine/Compose y un modelo conversacional habilitado en OpenCode. Clona y configura el proyecto **una sola vez** siguiendo la [instalación con Docker](README.md#instalación-completa-con-docker-powershell) (Windows) o [WSL/Linux](README.md#wsl--linux). Si ya lo instalaste, conserva su carpeta y `.env`; no vuelvas a clonar ni borres los volúmenes.

Dentro del repositorio ejecuta `docker compose ps`: `postgres` debe estar `healthy`. El MCP se inicia a demanda; **no** ejecutes `docker compose up -d mcp`. A partir de aquí, `REPO` significa la ruta absoluta a esa carpeta: es la que usará el MCP aunque abras OpenCode desde otro proyecto.

## 2. Copia el agente a la ubicación global

El archivo global es `~/.config/opencode/agents/azeroth-companion.md`. Si ya existe, revísalo antes de copiar: el archivo de este repositorio podría reemplazar instrucciones personalizadas. **No modifiques** `.opencode/agents/azeroth-companion.md` para esta instalación.

### PowerShell (OpenCode en Windows)

Abre PowerShell en la carpeta del repositorio:

```powershell
$repo = (Resolve-Path .).Path
$agentDir = Join-Path $HOME '.config/opencode/agents'
$agentFile = Join-Path $agentDir 'azeroth-companion.md'
if (Test-Path $agentFile) { throw 'El agente global ya existe; revisa su contenido antes de reemplazarlo.' }
New-Item -ItemType Directory -Path $agentDir -Force | Out-Null
Copy-Item '.opencode/agents/azeroth-companion.md' $agentFile
$repo.Replace('\', '/')  # Anota esta ruta para cwd en el paso 3
```

### WSL / Linux (OpenCode dentro de Linux)

Desde la carpeta del repositorio:

```sh
repo=$(pwd -P)
agent="$HOME/.config/opencode/agents/azeroth-companion.md"
if [ -e "$agent" ]; then echo 'El agente global ya existe; revísalo antes de reemplazarlo.' >&2; exit 1; fi
mkdir -p "$(dirname "$agent")"
cp .opencode/agents/azeroth-companion.md "$agent"
printf 'Usa esta ruta como cwd: %s\n' "$repo"
```

**En ambos sistemas**, abre la **copia global** y agrega `model: openai/gpt-6-sol` al frontmatter YAML, entre `mode: primary` y `permissions:`. Es el modelo probado en esta instalación; si no lo tienes disponible, sustituye `openai/gpt-6-sol` por un `proveedor/modelo` que hayas conectado. Sin un modelo definido para el agente, en otros proyectos heredará el modelo predeterminado de allí, que puede no funcionar o no tener créditos. Conserva intactos el texto y las restricciones `shell`, `edit` y `subagent` del agente.

## 3. Configura el MCP global sin sobrescribir otras opciones

Edita `~/.config/opencode/opencode.jsonc` (**no** `cli.json`). Si no existe, créalo. Si ya existe, añade únicamente `mcp.servers.azeroth` al objeto existente; conserva los demás servidores, agentes, comentarios y configuraciones. Si ya hay un servidor llamado `azeroth`, revísalo antes de reemplazarlo. Usa la ruta absoluta `REPO` del paso 2 en `cwd`, con `/` también en Windows:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "azeroth": {
        "type": "local",
        "command": ["docker", "compose", "run", "--rm", "-T", "mcp"],
        "cwd": "C:/ruta/absoluta/a/wow-forever-agent",
        "timeout": { "startup": 120000, "execution": 600000 }
      }
    }
  }
}
```

En WSL/Linux, `cwd` sería, por ejemplo, `/home/usuario/wow-forever-agent`. **No pegues el ejemplo encima de una configuración existente**: es el contenido completo únicamente para una configuración global nueva. No agregues `default_agent` global: en otros proyectos podrás seguir usando Build u otro agente normalmente. El `opencode.jsonc` de este repositorio seguirá teniendo prioridad aquí; por eso su MCP local puede omitir `cwd` y utilizar esta misma carpeta.

## 4. Comprueba desde otra carpeta

Abre OpenCode en **otro proyecto** y selecciona `azeroth-companion`, o prueba desde su terminal:

```sh
opencode reload
opencode run --archived --agent azeroth-companion "Consulta la biblioteca local: ¿qué son los Legacy Points? Cita la fuente y no guardes datos."
opencode mcp list
```

La prueba debe consultar `wow_search_knowledge`, citar una URL indexada y mostrar `azeroth connected`. Si `mcp list` no lo muestra aún, abre una sesión en ese proyecto y realiza la consulta: el MCP puede inicializarse al cargar la ubicación. Comprueba también desde la carpeta original con `opencode mcp list`. Seleccionar el agente en una sesión existente **no cambia necesariamente el modelo ya seleccionado en esa sesión**; elige el modelo configurado para el agente si fuera necesario.

## Límites y mantenimiento

- Docker y el repositorio principal deben seguir accesibles; si mueves la carpeta, actualiza `cwd`. En WSL y Windows cada instalación de OpenCode tiene **su propia** configuración global; usa rutas válidas para el entorno donde ejecutas `opencode`.
- Todas las sesiones comparten los mismos documentos, personajes y preferencias de **una** base. El MCP global puede arrancar en proyectos donde no vayas a usar el agente y consumir recursos; no se convierte en predeterminado por este procedimiento.
- Para actualizar el código: `git pull`, `docker compose build mcp` y `docker compose run --rm -T mcp alembic upgrade head` desde `REPO`; después `opencode reload`. Si cambian las instrucciones del agente en Git, revisa y vuelve a copiar los cambios a la copia global **sin sobrescribir tus ajustes**.
- Para desinstalar solo la integración global, elimina la entrada global `mcp.servers.azeroth` y la copia global `agents/azeroth-companion.md` después de confirmar que no las utilizas para otra instalación. No borres `.env` ni los volúmenes Docker si deseas conservar tus datos.

Referencias: [agentes globales](https://opencode.ai/docs/agents), [servidores MCP locales y `cwd`](https://opencode.ai/docs/mcp-servers), [precedencia de configuración](https://opencode.ai/docs/config).
