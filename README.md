# Patent Table Extractor (Local Docker App)

This repo provides a minimal FastAPI‑based web application that locates tables inside a set of patent XML files and (stub) extracts them into a single CSV, returned to the user from a simple HTML page.

> **Important** – heavy tasks such as LLM relevance checking and XML→CSV parsing are stubbed so the stack runs without extra credentials or compute. Swap the corresponding functions in `backend/utils.py` with real implementations when ready.

---

## ▶️  Quick Start

```bash
# 1.  Create & edit .env
cp .env.example .env
# (optionally put your OpenAI key if you hook up real relevance checks)

# 2.  Build & run
docker compose up --build

# 3.  Open browser
http://localhost:8000