"""Google Sheets is the shop's inventory book. The agent reads it freely;
writing back is deliberately not something the agent can do on its own."""

import os
from datetime import datetime, timezone

import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
RANGE = "Inventory!A1:F50"

HEADERS = ["Item", "Unit", "Current Stock", "Reorder Level", "Supplier", "Last Updated"]

_service = None


def _credentials():
    """Locally, a downloaded key file. On Cloud Run, the service the container
    runs as - so no key ever ships with the image."""
    key_file = os.environ.get("SERVICE_ACCOUNT_FILE")
    if key_file and os.path.exists(key_file):
        return service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    credentials, _ = google.auth.default(scopes=SCOPES)
    return credentials


def _sheets():
    global _service
    if _service is None:
        _service = build("sheets", "v4", credentials=_credentials(), cache_discovery=False)
    return _service


def _sheet_id():
    return os.environ["INVENTORY_SHEET_ID"]


def _rows():
    """Raw rows from the sheet, header included."""
    result = (
        _sheets()
        .spreadsheets()
        .values()
        .get(spreadsheetId=_sheet_id(), range=RANGE)
        .execute()
    )
    return result.get("values", [])


def _as_records(rows):
    records = []
    for index, row in enumerate(rows[1:], start=2):  # row 1 is the header
        padded = row + [""] * (len(HEADERS) - len(row))
        try:
            stock = int(padded[2] or 0)
            reorder = int(padded[3] or 0)
        except ValueError:
            continue
        records.append(
            {
                "row": index,
                "item": padded[0],
                "unit": padded[1],
                "stock": stock,
                "reorder_level": reorder,
                "supplier": padded[4],
                "last_updated": padded[5],
            }
        )
    return records


def load_inventory():
    """Every item in the sheet, as plain dicts. Used by the UI and the tools."""
    return _as_records(_rows())


# --- Agent-facing tools ------------------------------------------------------


def check_inventory(item: str = "") -> dict:
    """Read the current stock levels from the shop's inventory sheet.

    Args:
        item: Optional item name to look up. Leave empty to get everything.

    Returns:
        The matching inventory rows, each with current stock and reorder level.
    """
    records = load_inventory()
    if item:
        needle = item.strip().lower()
        records = [r for r in records if needle in r["item"].lower()]
        if not records:
            return {"status": "not_found", "message": f"No item matching '{item}'."}
    return {"status": "ok", "items": records}


def find_items_below_reorder_level() -> dict:
    """List every item whose stock has fallen to or below its reorder level.

    Returns:
        The items that need restocking, with how many units short they are.
    """
    low = [
        {**r, "shortfall": r["reorder_level"] - r["stock"]}
        for r in load_inventory()
        if r["stock"] <= r["reorder_level"]
    ]
    if not low:
        return {"status": "ok", "items": [], "message": "Everything is above its reorder level."}
    return {"status": "ok", "items": low}


def propose_restock(item: str, quantity: int, reason: str) -> dict:
    """Propose a restock for one item. This does NOT change the sheet.

    The proposal is handed to a human, who approves or rejects it. Use this
    whenever stock needs to be raised - never claim you have updated anything.

    Args:
        item: The exact item name as it appears in the inventory.
        quantity: How many units to add.
        reason: One short sentence on why this restock is needed.

    Returns:
        The pending proposal, awaiting human approval.
    """
    matches = [r for r in load_inventory() if r["item"].lower() == item.strip().lower()]
    if not matches:
        return {"status": "not_found", "message": f"'{item}' is not in the inventory."}
    if quantity <= 0:
        return {"status": "invalid", "message": "Quantity must be greater than zero."}

    record = matches[0]
    return {
        "status": "awaiting_approval",
        "proposal": {
            "row": record["row"],
            "item": record["item"],
            "unit": record["unit"],
            "current_stock": record["stock"],
            "quantity": quantity,
            "new_stock": record["stock"] + quantity,
            "supplier": record["supplier"],
            "reason": reason,
        },
        "message": "Proposal created. A human must approve it before the sheet changes.",
    }


# --- Not a tool: only the app calls this, and only after a human approves ----


def apply_restock(proposal: dict) -> dict:
    """Write an approved restock back to the sheet.

    Deliberately not registered as an agent tool. The model can propose;
    only an approved proposal reaches this function.
    """
    row = proposal["row"]
    new_stock = proposal["new_stock"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Only stock and the timestamp change. Reorder level and supplier are left
    # alone - writing the whole C:F block would blank the columns we don't set.
    _sheets().spreadsheets().values().batchUpdate(
        spreadsheetId=_sheet_id(),
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"Inventory!C{row}", "values": [[new_stock]]},
                {"range": f"Inventory!F{row}", "values": [[stamp]]},
            ],
        },
    ).execute()

    return {"status": "applied", "item": proposal["item"], "new_stock": new_stock}
