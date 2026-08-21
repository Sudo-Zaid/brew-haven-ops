# Brew Haven Ops — Track 3

A productivity agent for a coffee shop, built for **Gen AI Academy APAC,
Cohort 3, Track 3**.

Ops watches the shop's inventory sheet and proposes restocks. It cannot
change anything on its own: every write goes through a human.

| Piece | What it does |
|---|---|
| `sheets_tools.py` | Reads with the Sheets API `values.get`, writes with `values.update` |
| `agent.py` | A Google ADK agent on Gemini with three read/propose tools |
| `app.py` | Streamlit UI with the approval queue |

## Human in the loop

`apply_restock` is deliberately **not** registered as an agent tool. The model
can only call `propose_restock`, which returns a pending proposal. The sheet
changes when the manager presses Approve, and not before.

## Running it

Deployed on Cloud Run as a dedicated service account, so no key ships in the
image. Locally it falls back to a key file named by `SERVICE_ACCOUNT_FILE`.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/streamlit run app.py
```
