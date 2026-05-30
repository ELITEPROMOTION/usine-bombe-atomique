import asyncio, asyncpg, os, subprocess, sys
async def migrate():
    try:
        sql = open('all_migrations.sql').read()
    except Exception as e:
        print("MIGRATION: no file:", e, flush=True); return
    conn = await asyncpg.connect(
        host=os.environ['POSTGRES_HOST'], port=int(os.environ.get('POSTGRES_PORT', 5432)),
        user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
        database=os.environ['POSTGRES_DB'], ssl='require')
    ok = err = 0
    for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
        try:
            await conn.execute(stmt); ok += 1
        except Exception:
            err += 1
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    has_users = any(r['tablename'] == 'users' for r in rows)
    print(f"MIGRATIONS DONE: {ok} ok, {err} err, {len(rows)} tables, users={'YES' if has_users else 'NO'}", flush=True)
    await conn.close()
asyncio.run(migrate())
port = os.environ.get('PORT', '8000')
print(f"STARTING API on port {port}", flush=True)
subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port])
