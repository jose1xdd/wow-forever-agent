#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    password=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    umask 077
    cat > .env <<EOF
POSTGRES_DB=azeroth_knowledge
POSTGRES_USER=azeroth
POSTGRES_PASSWORD=$password
POSTGRES_PORT=5439
DATABASE_URL=postgresql+psycopg://azeroth:$password@127.0.0.1:5439/azeroth_knowledge
HF_HOME=.cache/huggingface
WOW_EMBEDDINGS_ENABLED=true
EOF
    echo 'Created local .env (ignored by Git).'
else
    echo 'Using existing .env; credentials unchanged.'
fi

docker compose up -d postgres
docker compose build mcp
docker compose run --rm -T mcp alembic upgrade head
docker compose run --rm -T mcp python -m wow_knowledge.cli init-sources

docker compose run --rm -T mcp python -m wow_knowledge.cli ingest 'https://worldofwarcraft.blizzard.com/en-us/news/24307383' || echo 'Blizzard seed unavailable; retry later.'
docker compose run --rm -T mcp python -m wow_knowledge.cli ingest 'https://wowforeverbuilds.com/guide/affliction-drain-tank-warlock-leveling' || echo 'Community guide unavailable; retry later.'

echo 'Done. Start OpenCode here; check connection with: opencode mcp list'
