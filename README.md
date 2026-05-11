# Remedi Chronic Care — WhatsApp Chatbot

> AI-powered WhatsApp bot for chronic disease management in Sri Lanka.  
> Helps patients with diabetes, hypertension, and other chronic conditions manage their health through automated reminders, lab report analysis, teleconsultation booking, and direct doctor chat.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

| Feature | Description |
|---|---|
| 🩺 **Lab Report Analysis** | Upload PDF reports via WhatsApp → AI extracts values → instant alert (green/yellow/red/critical) |
| 🩸 **Blood Pressure Logging** | Log BP readings via chat; AI detects concerning trends nightly |
| 📅 **Teleconsultation Booking** | Browse available slots and book appointments |
| 🏠 **Home Visit Requests** | Request nurse/doctor home visits (Colombo area) |
| 💬 **Doctor Chat** | Real-time text consultation with a doctor |
| 💡 **Health Tips** | AI-generated, condition-specific tips 2× per week |
| 🩸 **Blood Test Reminders** | Scheduled reminders for overdue or upcoming tests |
| 📊 **Annual Reports** | Year-in-review summary sent on enrollment anniversary |

---

## Architecture

```
WhatsApp Cloud API
        │
        ▼
   FastAPI (main.py)
        │
   ┌────┴────┐
   │ Routes  │  webhook / admin / doctor / auth
   └────┬────┘
        │
   ConversationGraph (LangGraph)
        │
   ┌────┴──────────────────────────┐
   │         Handlers              │
   │  BP · Report · Teleconsult    │
   │  HomeVisit · DoctorChat       │
   └────┬──────────────────────────┘
        │
   ┌────┴────────────────────────────────┐
   │           Services                  │
   │  MongoDB · Redis · MinIO · OpenAI   │
   └─────────────────────────────────────┘

ARQ Worker (separate process)
  ├── Blood test reminders   (daily 8am)
  ├── Health tips            (Mon + Thu 9am)
  ├── Appointment reminders  (every hour)
  ├── BP pattern analysis    (daily 8pm)
  └── Annual reports         (daily 7am)

Monitoring
  ├── Prometheus  → FastAPI /metrics
  ├── Grafana     → dashboards
  └── Loki        → log aggregation
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Conversation | LangGraph state machine |
| Database | MongoDB (Motor async driver) |
| Cache / State | Redis (redis-py async) |
| Object Storage | MinIO (lab report PDFs) |
| AI / LLM | OpenRouter → Claude / GPT-4o |
| PDF Extraction | pdfplumber |
| Background Jobs | ARQ (async Redis queue) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Monitoring | Prometheus + Grafana + Loki |
| Containerisation | Docker + Docker Compose |

---

## Quick Start

### Prerequisites

- Docker Desktop
- A Meta WhatsApp Business API account with a phone number
- An [OpenRouter](https://openrouter.ai) API key
- (Optional) A MongoDB Atlas URI if not using the bundled Docker container

### 1. Clone and configure

```bash
git clone https://github.com/AhamedShaa/remedi-whatsapp-chatbot.git
cd remedi-whatsapp-chatbot
cp .env.example .env
```

Edit `.env` and fill in every value (see [Environment Variables](#environment-variables) below).

### 2. Start all services

```bash
docker compose up -d
```

This starts: `api` · `worker` · `mongodb` · `redis` · `minio` · `prometheus` · `grafana` · `loki`

### 3. Seed the database

```bash
# Create the first admin user
docker compose exec api python scripts/create_admin.py

# (Optional) Create a test patient
docker compose exec api python scripts/create_test_patient.py
```

### 4. Expose webhook via ngrok (local dev)

```bash
ngrok http 8000
```

Set the ngrok HTTPS URL as your Meta webhook URL:  
`https://<ngrok-id>.ngrok.io/webhook`

### 5. Verify

```
GET  /health         → service status
GET  /metrics        → Prometheus metrics
GET  /docs           → Swagger UI
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
# WhatsApp / Meta Cloud API
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=        # any random string — must match Meta webhook config
WHATSAPP_API_VERSION=v24.0

# AI
OPENROUTER_API_KEY=

# MongoDB
MONGO_PASSWORD=
MONGODB_URI=mongodb://remedi:<MONGO_PASSWORD>@mongodb:27017/remedi_chronic_care?authSource=admin
DB_NAME=remedi_chronic_care

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
REDIS_PASSWORD=

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=remedi
MINIO_SECRET_KEY=
MINIO_BUCKET_REPORTS=patient-reports
MINIO_SECURE=false

# Auth (JWT)
JWT_SECRET=                   # openssl rand -hex 32
JWT_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# App
ENVIRONMENT=development
PORT=8000

# Business
REGISTRATION_FORM_URL=
PAYMENT_LINK=
SUPPORT_PHONE=
EMERGENCY_PHONE=
GOOGLE_FORM_SECRET=
ADMIN_EMAIL=
ADMIN_PHONE=
```

---

## API Reference

### Public

| Method | Path | Description |
|---|---|---|
| `GET` | `/webhook` | Meta webhook verification |
| `POST` | `/webhook` | Incoming WhatsApp messages |
| `POST` | `/google-form-submission` | Patient registration from Google Form |
| `GET` | `/health` | Service health check |
| `GET` | `/metrics` | Prometheus metrics |

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Login (admin or doctor) → JWT |
| `POST` | `/auth/refresh` | Refresh access token |

### Admin (`Bearer` — role: `admin`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/stats` | Dashboard statistics |
| `GET` | `/admin/patients` | List patients (paginated) |
| `GET` | `/admin/patients/{id}` | Single patient detail |
| `POST` | `/admin/approve-patient` | Approve enrollment |
| `POST` | `/admin/approve-by-phone` | Quick approve by phone (testing) |
| `POST` | `/admin/trigger-job` | Manually enqueue an ARQ job |
| `GET` | `/admin/audit-logs` | NDHGS audit log entries |

### Doctor (`Bearer` — role: `doctor` or `admin`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/doctor/my-patients` | Patients assigned to this doctor |
| `GET` | `/doctor/patients/{id}` | Full patient detail |
| `GET` | `/doctor/patients/{id}/reports` | Lab reports with MinIO download URLs |
| `GET` | `/doctor/patients/{id}/bp-history` | 90-day BP chart data |
| `POST` | `/doctor/patients/{id}/notes` | Save consultation note |
| `GET` | `/doctor/queue` | Active doctor-chat queue |

Interactive docs available at `http://localhost:8000/docs`.

---

## Project Structure

```
remedi-whatsapp-chatbot/
├── main.py                    # FastAPI app, singletons, lifecycle
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
│
├── config/
│   └── settings.py            # Pydantic-settings env loader
│
├── routes/
│   ├── webhook.py             # WhatsApp webhook + Google Form
│   ├── auth.py                # JWT login / refresh
│   ├── admin.py               # Admin endpoints
│   └── doctor.py              # Doctor endpoints
│
├── workflows/
│   └── conversation_graph.py  # LangGraph state machine
│
├── handlers/
│   ├── bp_handler.py
│   ├── report_handler.py
│   ├── teleconsult_handler.py
│   ├── home_visit_handler.py
│   └── doctor_chat_handler.py
│
├── ai/
│   ├── client.py              # OpenRouter async client (retry + logging)
│   └── pdf_extractor.py       # pdfplumber async wrapper
│
├── database/
│   ├── mongodb.py             # Motor async MongoDB operations
│   ├── redis_client.py        # Redis async client + conversation state
│   └── minio_client.py        # MinIO object storage
│
├── core/
│   ├── security.py            # JWT + bcrypt
│   ├── dependencies.py        # FastAPI dependency injection
│   └── audit.py               # NDHGS compliance audit middleware
│
├── jobs/
│   ├── worker.py              # ARQ WorkerSettings + all job functions
│   ├── health_tips.py         # Static tip library
│   └── reminder_jobs.py       # Appointment reminder helpers
│
├── models/
│   ├── patient.py
│   ├── report.py
│   ├── appointment.py
│   ├── bp_reading.py
│   └── doctor.py
│
├── utils/
│   ├── whatsapp_client.py     # WhatsApp Cloud API wrapper
│   └── logger.py              # Loguru structured logging
│
├── monitoring/
│   ├── prometheus.yml
│   └── loki-config.yml
│
└── scripts/
    ├── create_admin.py
    └── create_test_patient.py
```

---

## Running the ARQ Worker

The background job worker runs as a separate process (already handled by Docker Compose):

```bash
# Docker Compose (recommended)
docker compose up worker

# Local dev
python jobs/worker.py
# or
arq jobs.worker.WorkerSettings
```

Trigger any job manually via the admin API:

```bash
curl -X POST http://localhost:8000/admin/trigger-job \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"job_name": "blood_test_reminders"}'
```

Valid `job_name` values: `blood_test_reminders` · `health_tips` · `appointment_reminders` · `bp_patterns` · `annual_reports`

---

## Monitoring

| Service | URL | Credentials |
|---|---|---|
| Grafana | `http://localhost:3001` | admin / admin |
| Prometheus | `http://localhost:9090` | — |
| Loki | `http://localhost:3100` | — |
| MinIO Console | `http://localhost:9001` | remedi / `$MINIO_SECRET_KEY` |

In Grafana, add Prometheus (`http://prometheus:9090`) and Loki (`http://loki:3100`) as data sources.

---

## Security

- All admin and doctor routes require a signed JWT (`Authorization: Bearer <token>`)
- Passwords hashed with bcrypt (passlib)
- Audit log written for every authenticated request (NDHGS compliance)
- Secrets loaded exclusively from environment variables — never committed
- MinIO report access via short-lived presigned URLs

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m "feat: add my feature"`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.
