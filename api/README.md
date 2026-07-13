# MECA_CUP API (`api/routes.py`)

FastAPI + aiomysql로 `baggage_system` MySQL에 붙는 API 서버.
OCI VM에 `dashboard.service`(systemd)로 상시 배포되어 있고, SafeClaim iOS 앱과 대시보드가 이걸 사용한다.

## 실행

```bash
DB_HOST=<db host> DB_USER=sync_user DB_PASSWORD=<pw> DB_NAME=baggage_system \
  uvicorn api.routes:app --host 0.0.0.0 --port 8000
```

## 데이터 모델

- **passenger**: 보딩패스(BCBP) 정보 — `pnr_code`, `e_ticket`, `bcbp_raw`, `flight_number` 등. 승객 1명 = 1행.
- **baggage**: 수하물 1개 = 1행. `owner_id`로 `passenger.id`를 참조 (1인 1수하물 가정). `rfid_tag`는 UNIQUE.
  - `status`: `REGISTERED` → `CIRCULATING` → `READY` → `DELIVERED` (또는 `DEFECT`)
- **event_log**: baggage 상태가 바뀔 때마다 남는 이력 (`baggage_id` 참조).
- **plc_log**: 로컬 게이트웨이(`main.py`)가 읽은 PLC 값. 60초마다 로컬→클라우드로 배치 동기화됨.

## 앱 사용 흐름 (추정)

```
1. POST /api/passenger/match     승객 로그인 (보딩패스 스캔)
2. GET  /api/baggage/by_passenger/{id}   앱이 주기적으로 폴링해서 상태 표시
3. POST /api/baggage/confirm_delivery    승객이 수취대에서 QR 스캔 → DELIVERED 확정

(사용미정)
POST /api/checkin             수하물 접수 (RFID 태그 부착) — 접수대 직원/게이트웨이가 호출할 것으로 추정

(라즈베리파이쪽 rfid가 스캔되면 그때 호출하여 상태 갱신)
PUT  /api/baggage/{rfid_tag}/state    상태 갱신 — 아직 실제로 호출하는 쪽(PLC/RFID 연동)이 코드에 없음

```

## 엔드포인트

### 조회 (대시보드/디버그용)

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | HTML 대시보드 — baggage/passenger/event_log/plc_log 최근 50건, 5초 자동 새로고침 |
| GET | `/api/plc_log?limit=50` | PLC 로그 |
| GET | `/api/baggage?limit=50` | 전체 수하물 |
| GET | `/api/passenger?limit=50` | 전체 승객 |
| GET | `/api/event_log?limit=50` | 전체 이벤트 로그 |
| GET | `/api/baggage/by_qr/{qr_code}` | `baggage.qr_code`로 조회 (수취 확인 후에만 값이 채워짐) |

### 승객

**`POST /api/passenger/match`** — 보딩패스로 승객 매칭 (로그인)
```json
// request
{ "bcbp_raw": "M1KIM/MINJUN ...", "pnr_code": "ABCDEF" }
// response: passenger 1행 (bcbp_raw 우선 매칭, 없으면 pnr_code로 재시도) / 없으면 404
```

**`GET /api/passenger/{passenger_id}`** — 세션 복원용 재조회. 없으면 404.

### 수하물

**`POST /api/checkin`** — 수하물 접수 (RFID 태그를 승객에게 연결)-(사용미정)
```json
// request
{ "bcbp_raw": "...", "pnr_code": "...", "rfid_tag": "RFID-001" }
// response: baggage 1행 (status=REGISTERED로 생성/리셋)
```
- 승객을 못 찾으면 404
- 같은 `rfid_tag`로 다시 호출하면 새 행이 아니라 기존 행을 갱신함 (UNIQUE 제약)

**`GET /api/baggage/by_passenger/{passenger_id}`** — 그 승객의 최신 수하물 1건. 없으면 404.

**`PUT /api/baggage/{rfid_tag}/state`** — 상태 갱신
```json
// request
{ "status": "CIRCULATING", "inspection_result": "NORMAL" }
```
- `status`는 `REGISTERED`/`CIRCULATING`/`READY`/`DELIVERED`/`DEFECT` 중 하나만 허용 (아니면 400)
- `rfid_tag`가 없으면 404
- `status=DELIVERED`면 `delivered_at`이 자동으로 채워짐
- 호출될 때마다 `event_log`에 이력 남음

**`POST /api/baggage/confirm_delivery`** — 승객 앱의 수취 확인
```json
// request
{ "passenger_id": 3, "qr_code": "scanned-qr-value" }
```
- 그 승객의 최신 수하물을 찾아 `qr_code`를 기록하고 `status=DELIVERED`, `delivered_at=NOW()`로 갱신
- 수취대 센서 하드웨어가 없는 지금 단계의 임시 로직

## 알아둘 것
- `PUT .../state`를 실제로 호출하는 쪽이 아직 없어서, 지금은 `CIRCULATING`/`READY`/`DEFECT` 상태로 자동 전환되는 경로가 없음 (수동 테스트로만 가능)
