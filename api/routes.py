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

plc_manager = None

pool = None

def set_plc_manager(manager):
    global plc_manager
    plc_manager = manager

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


class PassengerMatchRequest(BaseModel):
    bcbp_raw: str
    pnr_code: str


@app.post("/api/passenger/match")
async def match_passenger(req: PassengerMatchRequest):
    """SafeClaim 앱 로그인: 스캔한 보딩패스(BCBP)를 passenger 테이블과 매칭한다.
    체크인 시 저장된 bcbp_raw 원문과 우선 비교하고, 스캐너 인식 편차(공백 등)에 대비해
    pnr_code로도 재시도한다."""
    row = await fetch_one(
        "SELECT * FROM passenger WHERE bcbp_raw = %s ORDER BY id DESC LIMIT 1",
        (req.bcbp_raw,),
    )
    if not row:
        row = await fetch_one(
            "SELECT * FROM passenger WHERE pnr_code = %s ORDER BY id DESC LIMIT 1",
            (req.pnr_code,),
        )
    if not row:
        raise HTTPException(404, "no matching passenger")
    return row


@app.get("/api/passenger/{passenger_id}")
async def passenger_by_id(passenger_id: int):
    """세션 복원용: passenger_id로 승객 정보를 다시 조회한다."""
    row = await fetch_one("SELECT * FROM passenger WHERE id = %s", (passenger_id,))
    if not row:
        raise HTTPException(404, "passenger not found")
    return row


@app.get("/api/event_log")
async def event_log(limit: int = 50):
    return await fetch_all("SELECT * FROM event_log ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/baggage/by_qr/{qr_code}")
async def baggage_by_qr(qr_code: str):
    return await fetch_all(
        "SELECT * FROM baggage WHERE qr_code = %s ORDER BY id DESC", (qr_code,)
    )


@app.get("/api/baggage/by_passenger/{passenger_id}")
async def baggage_by_passenger(passenger_id: int):
    """SafeClaim 대시보드 폴링용: 승객의 수하물 상태 (1인 1수하물 가정, 최신 1건 반환)."""
    row = await fetch_one(
        "SELECT * FROM baggage WHERE owner_id = %s ORDER BY id DESC LIMIT 1",
        (passenger_id,),
    )
    if not row:
        raise HTTPException(404, "no baggage found for passenger")
    return row


class CheckinRequest(BaseModel):
    bcbp_raw: str = ""
    pnr_code: str = ""
    rfid_tag: str


@app.post("/api/checkin")
async def checkin(req: CheckinRequest):
    """수하물 접수: 보딩패스(bcbp_raw 우선, 없으면 pnr_code)로 승객을 찾아
    그 승객 소유의 baggage 행을 만들거나(REGISTERED로 리셋) 갱신한다."""
    passenger = None
    if req.bcbp_raw:
        passenger = await fetch_one(
            "SELECT * FROM passenger WHERE bcbp_raw = %s ORDER BY id DESC LIMIT 1", (req.bcbp_raw,)
        )
    if not passenger and req.pnr_code:
        passenger = await fetch_one(
            "SELECT * FROM passenger WHERE pnr_code = %s ORDER BY id DESC LIMIT 1", (req.pnr_code,)
        )
    if not passenger:
        raise HTTPException(404, "no matching passenger")

    flight_no = f"{passenger['carrier_code'] or ''}{passenger['flight_number'] or ''}"

    await execute(
        """
        INSERT INTO baggage (rfid_tag, baggage_tag, owner_id, flight_no, status)
        VALUES (%s, %s, %s, %s, 'REGISTERED')
        ON DUPLICATE KEY UPDATE
            baggage_tag = VALUES(baggage_tag),
            owner_id = VALUES(owner_id),
            flight_no = VALUES(flight_no),
            status = 'REGISTERED',
            qr_code = NULL,
            inspection_result = NULL,
            delivered_at = NULL
        """,
        (req.rfid_tag, passenger["baggage_tag"], passenger["id"], flight_no),
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
    inspection_result: Optional[str] = None


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
            inspection_result = COALESCE(%s, inspection_result),
            delivered_at = CASE WHEN %s = 'DELIVERED' THEN NOW() ELSE delivered_at END
        WHERE rfid_tag = %s
        """,
        (req.status, req.inspection_result, req.status, rfid_tag),
    )

    await execute(
        "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
        (baggage_row["id"], req.status, f"상태 변경: {req.status}"),
    )

    return await fetch_one("SELECT * FROM baggage WHERE rfid_tag = %s", (rfid_tag,))


class ConfirmDeliveryRequest(BaseModel):
    passenger_id: int
    qr_code: str


@app.post("/api/baggage/confirm_delivery")
async def confirm_delivery(req: ConfirmDeliveryRequest):
    """SafeClaim 앱의 수취 확인 스캔: 로그인한 승객이 수취대에서 QR을 스캔하면 그 값을
    본인 수하물(owner_id로 식별) 레코드의 qr_code에 기록하고 DELIVERED로 갱신한다
    (수취대 센서 하드웨어 완성 전 임시 로직)."""

    baggage_row = await fetch_one(
        "SELECT * FROM baggage WHERE owner_id = %s ORDER BY id DESC LIMIT 1",
        (req.passenger_id,),
    )
    if not baggage_row:
        raise HTTPException(404, "no baggage found for passengesr")

    # await execute(
    #     "UPDATE baggage SET qr_code = %s, status = 'DELIVERED', delivered_at = NOW() WHERE id = %s",
    #     (req.qr_code, baggage_row["id"]),
    # )
    # # QR_CODE:2 → 2
    # position = int(req.qr_code.split(":")[1])

    # if plc_manager:
    #     plc_manager.write_value(
    #         "D100",
    #         position
    # )
    # else:
    #     print("[API]PLC Manager 없음")
    await execute(
        "UPDATE baggage SET qr_code = %s, status = 'DELIVERED', delivered_at = NOW() WHERE id = %s",
        (req.qr_code, baggage_row["id"]),
    )


    try:
        position = int(req.qr_code.split(":")[1])
    except Exception:
        raise HTTPException(400, "invalid qr format")


    if plc_manager:
        plc_manager.write_value(
            "D100",
            position
        )
    else:
        print("[API] PLC Manager 없음")

    await execute(
        "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
        (baggage_row["id"], "DELIVERED", "승객 앱 QR 스캔으로 수취 확인"),
    )

    return await fetch_one("SELECT * FROM baggage WHERE id = %s", (baggage_row["id"],))