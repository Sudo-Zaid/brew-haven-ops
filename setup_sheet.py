"""One-off: create the inventory spreadsheet, fill it, and share it with the
manager's Google account. Run once; it prints the sheet id."""

import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

KEY = "C:/genai/track3/.secrets/ops-sa.json"
SHEET_ID = "1aKwKKHbOCGDkylqIy3VywEI3uiigBtTl-hE_EYGxJ9o"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ROWS = [
    ["Item", "Unit", "Current Stock", "Reorder Level", "Supplier", "Last Updated"],
    ["Espresso Beans (house blend)", "kg", "4", "10", "Kohistan Roasters", "2026-08-19 08:00 UTC"],
    ["Single Origin Beans (Yirgacheffe)", "kg", "12", "5", "Kohistan Roasters", "2026-08-19 08:00 UTC"],
    ["Full Cream Milk", "litre", "18", "40", "Dairy Fresh Rawalpindi", "2026-08-20 06:30 UTC"],
    ["Oat Milk", "litre", "9", "12", "Alt Milk Co", "2026-08-20 06:30 UTC"],
    ["Almond Milk", "litre", "14", "10", "Alt Milk Co", "2026-08-19 08:00 UTC"],
    ["Paper Cups 12oz", "piece", "260", "500", "PackWell Islamabad", "2026-08-18 11:15 UTC"],
    ["Paper Cups 8oz", "piece", "740", "500", "PackWell Islamabad", "2026-08-18 11:15 UTC"],
    ["Cup Lids", "piece", "420", "500", "PackWell Islamabad", "2026-08-18 11:15 UTC"],
    ["Matcha Powder", "kg", "1", "2", "Kyoto Leaf Imports", "2026-08-17 09:45 UTC"],
    ["Chocolate Syrup", "bottle", "7", "6", "Sweet Supply", "2026-08-19 08:00 UTC"],
    ["Butter Croissants (frozen)", "piece", "36", "60", "Bake House Jhelum", "2026-08-20 06:30 UTC"],
    ["Napkins", "pack", "22", "15", "PackWell Islamabad", "2026-08-16 14:00 UTC"],
]


def main():
    creds = service_account.Credentials.from_service_account_file(KEY, scopes=SCOPES)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    sheet_id = SHEET_ID

    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Inventory!A1",
        valueInputOption="USER_ENTERED",
        body={"values": ROWS},
    ).execute()

    # Bold header row, freeze it, and widen the item column.
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                        "properties": {"pixelSize": 260},
                        "fields": "pixelSize",
                    }
                },
            ]
        },
    ).execute()

    print("SHEET_ID:", sheet_id)
    print("URL: https://docs.google.com/spreadsheets/d/" + sheet_id)


if __name__ == "__main__":
    sys.exit(main())
