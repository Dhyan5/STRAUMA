# AI-Based Real-Time Stress & Trauma Assessment Module

> **Disclaimer:** Prototype for demonstration purposes. Not a diagnostic tool. All risk flags are reviewed by trained personnel.

## Overview
This is a demoable prototype of an AI-assisted Stress & Trauma Assessment Module that plugs into a simulated version of the National Helpline Against Atrocities (14566) and its Integrated Portal. It assists human counsellors by routing and prioritizing cases using a Stress Vulnerability Index (SVI). **It never replaces clinical judgment, and it never presents an automated conclusion as a diagnosis.**

## Features
- **Multi-channel intake (simulated):** Text chat, voice upload, and IVRS-style keypad input.
- **NLP & Speech Analytics Engine:** Analyzes text sentiment, matches risk lexicons, and extracts vocal stress heuristics.
- **Stress Vulnerability Index (SVI):** Composite score determining risk level (Low, Moderate, High, Critical) with a mandatory human-in-the-loop Critical Override for severe indicators.
- **Counsellor, Admin, and Law Enforcement Dashboards.**
- **Multilingual UI Shell.**
- **Privacy and Consent:** Designed with data minimization and RBAC.

## Architecture
- **Frontend:** Next.js 14, React, Tailwind CSS, shadcn/ui.
- **Backend:** FastAPI (Python 3.11).
- **Data:** PostgreSQL (SQLite default for local demo), Redis.
- **NLP/Audio:** HuggingFace transformers, librosa (demo heuristics).

## Setup & Running Locally

1. Create a virtual environment for the backend and install dependencies:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Setup environment variables:
   ```bash
   cp .env.example .env
   ```

3. Run the backend api:
   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

4. Install and run frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## DPDP Act, 2023 Principles
- **Purpose Limitation:** Data is used exclusively for routing counseling/support.
- **Storage Limitation:** Audit logs exist, but raw chat data can be configured to expire.
- **Consent:** Explicit consent prompt required before starting interaction.
- **Breach Notification:** System logs detailed accesses to facilitate reporting.
