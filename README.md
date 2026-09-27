# STRAUMA — Stress & Trauma Assessment Module
### National Helpline Against Atrocities (NHAA - 14566)
> **SIH Problem Statement 26093** — Real-Time Stress & Trauma Assessment Layer for Helpline Triage

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📌 Executive Summary

**STRAUMA** is an explainable, auditable, real-time triage and distress scoring module designed for the **National Helpline Against Atrocities (NHAA - 14566)** under the Ministry of Social Justice and Empowerment.

Rather than acting as an inscrutable "black-box AI" replacing human judgment, STRAUMA sits between incoming victim interactions (multilingual chat, voice-call transcripts, IVRS, and portal complaints) and human counsellors or police desks. It calculates an auditable **Stress Vulnerability Index (SVI, 0–100)** to ensure that high-risk cases (immediate threats, severe violence, self-harm signals) are prioritized instantly.

---

## 🔑 Key Features

### 1. Transparent SVI Scoring Engine
The SVI is deterministically calculated and fully explainable across 4 weighted components:
- **Lexical Distress Density (30%)**: Domain-specific distress lexicons across English, Hindi, and transliterated Hinglish.
- **Sentiment & Urgency Intensity (30%)**: VADER-derived compound negativity combined with explicit temporal urgency markers (e.g., "right now", "outside my house", "abhi", "madad").
- **Context & Threat Multipliers (20%)**: Escalation factors such as recurring abuse, weapons, mob violence, and structural discrimination under the PoA Act.
- **Safety Hard Overrides (20% + Auto-Critical Flag)**: Zero-tolerance keyword triggers for imminent self-harm, active armed threats, or ongoing violence that force immediate **CRITICAL (SVI ≥ 85)** classification.

### 2. Multi-Channel Intake & Bilingual Consent
- **Victim-Facing Chat Widget**: Step-zero informed consent flow available in English and Hindi (compliant with digital privacy standards).
- **Automatic Language Detection**: Handles English, Hindi (Devanagari), and romanized Hinglish.
- **Simulated Voice / Call Transcript Ingestion**: Ingests transcribed calls from telephony/IVRS with timestamps.

### 3. Counsellor Triage & Operations Dashboard
- **Real-Time Priority Queue**: Sorted by SVI score and categorized into `CRITICAL`, `HIGH`, `MODERATE`, and `LOW`.
- **Distress Profile Radar Chart**: Breakdown across 5 axes: Threat, Violence, Isolation, Fear, and Urgency.
- **Transcript Highlighter**: Color-coded keyword attribution showing exactly which words drove the assessment.
- **Automated Next-Step Recommendations**: Tailored actions (emergency police dispatch, legal aid, trauma counselling, shelter referral).
- **Full Audit Trail**: Every score change, override, and counsellor action is logged with timestamps and operator IDs.

---

## 🏗️ System Architecture

```text
       [ Victim / Caller ]
                │
   ┌────────────┴────────────┐
   │                         │
[ Chat Widget ]     [ Voice / Transcript ]
   │                         │
   └────────────┬────────────┘
                ▼
       [ Intake Layer (FastAPI) ]
                │
                ▼
     [ Assessment Engine ]
     ├── Language Identification (EN / HI / Hinglish)
     ├── Distress Lexicon Matcher
     ├── Urgency & Context Analyzer
     └── Hard Override Circuit Breaker
                │
                ▼
   [ SVI Score & Risk Category ]
                │
                ▼
  [ Counsellor Operations Dashboard ]
  ├── Triage Queue (SVI-ranked)
  ├── Explainable Distress Radar
  ├── Highlighted Keyword Transcript
  └── Action Recommendations & Audit Log
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** and **npm**

---

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
# Windows:
python -m venv venv
.\venv\Scripts\activate
# Linux/macOS:
# python3 -m venv venv
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Seed the database with sample cases
python seed_data.py

# Start FastAPI dev server
uvicorn app.main:app --reload --port 8000
```

- **Backend API**: `http://localhost:8000`
- **Interactive OpenAPI/Swagger Docs**: `http://localhost:8000/docs`

---

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

- **Frontend App**: `http://localhost:5173`

---

## 📡 API Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/intake/` | Register new case from chat, voice note, or portal |
| `POST` | `/api/assess/` | Compute SVI score and distress breakdown for a case |
| `POST` | `/api/assess/quick` | Quick assessment preview without saving to database |
| `GET` | `/api/cases/` | Fetch case queue with risk and status filters |
| `GET` | `/api/cases/{case_id}` | Detailed case report, transcript, and audit history |
| `GET` | `/api/cases/stats` | High-level statistics for dashboard widgets and charts |
| `POST` | `/api/cases/{case_id}/override` | Counsellor manual override of risk category |
| `GET` | `/api/recommend/{case_id}` | Context-aware recommendations based on SVI profile |

---

## 🛡️ Ethical Safeguards & Compliance

1. **Human-in-the-Loop Always**: AI provides scoring recommendations; final triage classification and dispatch decisions remain in human hands.
2. **Deterministic Overrides**: Critical danger triggers (e.g., suicide, active assault) bypass heuristic calculations to ensure zero false-negatives on life safety.
3. **Auditability**: Counsellors can inspect the exact words and score weights that generated any assessment.
4. **Data Privacy**: No audio is permanently retained beyond regulatory triage periods; consent is explicitly captured prior to intake.

---

## 👥 Authors & Acknowledgments
Built for **Smart India Hackathon (SIH)** — Enhancing citizen safety, dignity, and rapid trauma intervention under the National Helpline Against Atrocities.
