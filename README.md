# Clippy

Chippy turns patent data extraction into a trivial task. Our solution uses user-defined descriptions of relevant data contexts and desired output columns to automatically produce tabular data from patents and execute SQL upon them. Chippy leverages LLMs to greatly simplify the extremely tedious task of sifting through patents riddled with OCR malformatting, low average relevance, and difficult table merging decisions.

---

## ▶️  Quick Start

```bash
# 1.  Create & edit .env
cp .env_template .env #populate your OpenAI key

# 2.  Build & run
docker compose up --build

# 3.  Open browser
http://localhost:8000
