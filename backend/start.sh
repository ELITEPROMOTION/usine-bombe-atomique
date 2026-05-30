#!/bin/sh
echo "=== UBA STARTUP: applying migrations ==="
python - << 'PYEOF'
import asyncio, asyncpg, os
async def main():
    try:
        sql = open('all_migrations.sql').read()
    except Exception as e:
        print("no migration file:", e); return
    conn = await asyncpg.connect(
        host=os.environ['POSTGRES_HOST'], port=int(os.environ.get('POSTGRES_PORT', 5432)),
        user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
        database=os.environ['POSTGRES_DB'], ssl='require')
    ok = err = 0
    for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
        try:
            await conn.execute(stmt); ok += 1
        except Exception as e:
            err += 1
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    has_users = any(r['tablename'] == 'users' for r in rows)
    print(f"=== MIGRATIONS: {ok} ok, {err} err, {len(rows)} tables, users={'YES' if has_users else 'NO'} ===")
    await conn.close()
asyncio.run(main())
PYEOF
echo "=== STARTING API ==="
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
