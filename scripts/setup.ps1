# Instalación reproducible para Windows; ejecutar desde cualquier directorio.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit code $LASTEXITCODE)." }
}

if (-not (Test-Path '.env')) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $password = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $lines = @(
        'POSTGRES_DB=azeroth_knowledge'
        'POSTGRES_USER=azeroth'
        "POSTGRES_PASSWORD=$password"
        'POSTGRES_PORT=5439'
        "DATABASE_URL=postgresql+psycopg://azeroth:${password}@127.0.0.1:5439/azeroth_knowledge"
        'HF_HOME=.cache/huggingface'
        'WOW_EMBEDDINGS_ENABLED=true'
    )
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) '.env'),
        (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Created local .env (ignored by Git).'
} else {
    Write-Host 'Using existing .env; credentials unchanged.'
}

docker compose version
Assert-Exit 'Docker Compose check'
docker compose up -d postgres
Assert-Exit 'PostgreSQL startup'
docker compose build mcp
Assert-Exit 'MCP image build'
docker compose run --rm -T mcp alembic upgrade head
Assert-Exit 'Database migrations'
docker compose run --rm -T mcp python -m wow_knowledge.cli init-sources
Assert-Exit 'Source registry'

# Initial public evidence; a temporary source error should not destroy the installation.
docker compose run --rm -T mcp python -m wow_knowledge.cli ingest 'https://worldofwarcraft.blizzard.com/en-us/news/24307383'
if ($LASTEXITCODE -ne 0) { Write-Warning 'Blizzard seed not indexed; retry later with the CLI or /wow-refresh.' }
docker compose run --rm -T mcp python -m wow_knowledge.cli ingest 'https://wowforeverbuilds.com/guide/affliction-drain-tank-warlock-leveling'
if ($LASTEXITCODE -ne 0) { Write-Warning 'Community guide not indexed; retry later with the CLI or /wow-refresh.' }

Write-Host 'Done. Start OpenCode from this folder; check connection with: opencode mcp list'
