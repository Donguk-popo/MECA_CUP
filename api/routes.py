import os

import pymysql
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "sync_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "baggage_system")


def fetch_recent_logs(limit=50):
    connection = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4"
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT device, value, created_at FROM plc_log ORDER BY id DESC LIMIT %s",
                (limit,)
            )
            return cursor.fetchall()
    finally:
        connection.close()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    rows = fetch_recent_logs()

    table_rows = "".join(
        f"<tr><td>{device}</td><td>{value}</td><td>{created_at}</td></tr>"
        for device, value, created_at in rows
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
def plc_log(limit: int = 50):
    rows = fetch_recent_logs(limit)
    return [
        {"device": device, "value": value, "created_at": created_at.isoformat()}
        for device, value, created_at in rows
    ]
