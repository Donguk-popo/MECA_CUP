import html
import os
from contextlib import asynccontextmanager
from typing import Optional

import aiomysql
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "sync_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "baggage_system")

VALID_STATUSES = {"REGISTERED", "CIRCULATING", "READY", "DELIVERED", "DEFECT"}

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


async def fetch_one(query, args=None):
    rows = await fetch_all(query, args)
    return rows[0] if rows else None


async def execute(query, args=None):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(query, args or ())
            return cursor.lastrowid, cursor.rowcount


def _render_table(rows):
    if not rows:
        return "<p class='empty'>(no rows)</p>"

    columns = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(col)}</th>" for col in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row[col])) if row[col] is not None else ''}</td>" for col in columns) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    baggage_rows, passenger_rows, event_rows, plc_rows = [
        await fetch_all(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 50")
        for table in ("baggage", "passenger", "event_log", "plc_log")
    ]

    return f"""
    <html>
        <head>
            <title>MECA_CUP DB Dashboard</title>
            <meta http-equiv="refresh" content="5">
            <style>
                body {{ font-family: -apple-system, sans-serif; margin: 24px; color: #222; }}
                h2 {{ margin-top: 32px; }}
                table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
                th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; white-space: nowrap; }}
                th {{ background: #f0f0f0; }}
                tr:nth-child(even) {{ background: #fafafa; }}
                .empty {{ color: #888; }}
            </style>
        </head>
        <body>
            <h1>MECA_CUP DB Dashboard</h1>
            <p>5초마다 자동 새로고침</p>

            <h2>Baggage</h2>
            {_render_table(baggage_rows)}

            <h2>Passenger</h2>
            {_render_table(passenger_rows)}

            <h2>Event Log</h2>
            {_render_table(event_rows)}

            <h2>PLC Log</h2>
            {_render_table(plc_rows)}
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


@app.get("/api/baggage/by_qr/{qr_code}")
async def baggage_by_qr(qr_code: str):
    return await fetch_all(
        "SELECT * FROM baggage WHERE qr_code = %s ORDER BY id DESC", (qr_code,)
    )


class UpdateStatusRequest(BaseModel):
    qr_code: str
    status: int


@app.post("/api/baggage/update_status")
async def update_status(req: UpdateStatusRequest):
    """테스트용: qr_code(승객 탑승권 QR, 여러 수하물 공유)로 찾은 모든 수하물의
    discharge_point에 status 값을 그대로 기록한다."""
    rows = await fetch_all("SELECT * FROM baggage WHERE qr_code = %s", (req.qr_code,))
    if not rows:
        raise HTTPException(404, "no baggage found for qr_code")

    await execute(
        "UPDATE baggage SET discharge_point = %s WHERE qr_code = %s",
        (req.status, req.qr_code),
    )

    for row in rows:
        await execute(
            "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
            (row["id"], "TEST_UPDATE", f"discharge_point 테스트 값 {req.status} 반영"),
        )

    return await fetch_all("SELECT * FROM baggage WHERE qr_code = %s", (req.qr_code,))


class CheckinRequest(BaseModel):
    qr_code: str
    rfid_tag: str


@app.post("/api/checkin")
async def checkin(req: CheckinRequest):
    passenger = await fetch_one(
        "SELECT * FROM passenger WHERE qr_code = %s", (req.qr_code,)
    )
    if not passenger:
        raise HTTPException(404, "passenger not found for qr_code")

    await execute(
        """
        INSERT INTO baggage (rfid_tag, owner_name, qr_code, flight_no, status)
        VALUES (%s, %s, %s, %s, 'REGISTERED')
        ON DUPLICATE KEY UPDATE
            owner_name = VALUES(owner_name),
            qr_code = VALUES(qr_code),
            flight_no = VALUES(flight_no),
            status = 'REGISTERED',
            segment = NULL,
            discharge_point = NULL,
            delivered_at = NULL,
            remark = NULL
        """,
        (req.rfid_tag, passenger["name"], req.qr_code, passenger["flight_no"]),
    )

    baggage_row = await fetch_one(
        "SELECT * FROM baggage WHERE rfid_tag = %s", (req.rfid_tag,)
    )
    await execute(
        "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
        (baggage_row["id"], "REGISTERED", "체크인 완료"),
    )
    return baggage_row


class StateUpdateRequest(BaseModel):
    status: str
    segment: Optional[int] = None
    discharge_point: Optional[int] = None
    inspection_result: Optional[str] = None
    remark: Optional[str] = None


@app.put("/api/baggage/{rfid_tag}/state")
async def update_baggage_state(rfid_tag: str, req: StateUpdateRequest):
    if req.status not in VALID_STATUSES:
        raise HTTPException(400, f"invalid status: {req.status}")

    baggage_row = await fetch_one(
        "SELECT * FROM baggage WHERE rfid_tag = %s", (rfid_tag,)
    )
    if not baggage_row:
        raise HTTPException(404, "rfid_tag not found")

    await execute(
        """
        UPDATE baggage
        SET status = %s,
            segment = %s,
            discharge_point = %s,
            inspection_result = COALESCE(%s, inspection_result),
            remark = COALESCE(%s, remark),
            delivered_at = CASE WHEN %s = 'DELIVERED' THEN NOW() ELSE delivered_at END
        WHERE rfid_tag = %s
        """,
        (
            req.status,
            req.segment,
            req.discharge_point,
            req.inspection_result,
            req.remark,
            req.status,
            rfid_tag,
        ),
    )

    await execute(
        "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
        (baggage_row["id"], req.status, f"상태 변경: {req.status}"),
    )

    return await fetch_one("SELECT * FROM baggage WHERE rfid_tag = %s", (rfid_tag,))
