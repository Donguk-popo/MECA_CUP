import os
from contextlib import asynccontextmanager

import aiomysql
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "sync_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "baggage_system")

pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await aiomysql.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )
    yield
    pool.close()
    await pool.wait_closed()


app = FastAPI(lifespan=lifespan)


async def fetch_all(query, args=None):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, args or ())
            return await cursor.fetchall()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    rows = await fetch_all("SELECT device, value, created_at FROM plc_log ORDER BY id DESC LIMIT 50")

    table_rows = "".join(
        f"<tr><td>{row['device']}</td><td>{row['value']}</td><td>{row['created_at']}</td></tr>"
        for row in rows
    )

    return f"""
    <html>
        <head>
            <title>MECA_CUP PLC Dashboard</title>
            <meta http-equiv="refresh" content="5">
        </head>
        <body>
            <h1>PLC Log</h1>
            <table border="1" cellpadding="6">
                <tr><th>Device</th><th>Value</th><th>Created At</th></tr>
                {table_rows}
            </table>
        </body>
    </html>
    """


@app.get("/api/plc_log")
async def plc_log(limit: int = 50):
    return await fetch_all("SELECT device, value, created_at FROM plc_log ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/baggage")
async def baggage(limit: int = 50):
    return await fetch_all("SELECT * FROM baggage ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/passenger")
async def passenger(limit: int = 50):
    return await fetch_all("SELECT * FROM passenger ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/event_log")
async def event_log(limit: int = 50):
    return await fetch_all("SELECT * FROM event_log ORDER BY id DESC LIMIT %s", (limit,))
