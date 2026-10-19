# Procurement Agent

Python 3.12+ skeleton for the Aron procurement exercise. Includes an OpenRouter
adapter, a connection check, and preliminary free-text quote review. Structured
extraction, validated calculations, and follow-up drafts are not implemented yet.

## Setup

```bash
cd /workspace/Procurement-Agent
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
# Edit .env locally: add your key and choose your model. Do not share the file.
set -a
. ./.env
set +a
.venv/bin/procurement-agent check
```

The CLI reads process environment variables; it does not automatically load .env.
Alternatively export OPENROUTER_API_KEY and OPENROUTER_MODEL directly. HTTPS access
to openrouter.ai and an account with access/credits for the selected model are
required. Each check/review sends a real API request and may incur charges.

## Review a packet

```bash
.venv/bin/procurement-agent review /path/to/quotes.txt
```

Input must be UTF-8 plain text (PDF parsing is not included). The packet is sent
to OpenRouter and its model provider. Output goes to stdout; redirect it to a file
to preserve a run. This first version produces model-generated preliminary analysis;
it does not validate evidence or calculations and cannot send email or place orders.
No automatic retries are made, to avoid unexpected duplicate requests/costs.

## Tests (no API key or network required)

```bash
.venv/bin/python -m unittest discover -s tests -v
```
