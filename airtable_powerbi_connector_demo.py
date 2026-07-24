"""
Airtable -> Power BI Automation Connector (PORTFOLIO DEMO)
============================================================

This is a sample/demo version of a connector pattern I built for a real
internship project. All data below is fictional and no real API keys,
base IDs, or company data are used anywhere in this file.

The problem this pattern solves:
    Power BI dashboards are often wired to *static* exports (a CSV or
    Excel file someone downloads and re-uploads). That means every
    number on the dashboard is only as fresh as the last manual export.

This script demonstrates the general shape of a fix:
    1. Pull live records straight from Airtable's API (with pagination,
       since Airtable caps each request at 100 records).
    2. Clean and reshape the data into a flat table Power BI can ingest.
    3. Write it somewhere Power BI can pick up automatically (a CSV in a
       watched folder, a database table, or a Power BI Push Dataset via
       the REST API) instead of a manual export.

Run this file directly to see it work end-to-end against fake sample
data (no network calls, no real API needed).
"""

import time
import json
import csv
from dataclasses import dataclass, asdict
from typing import List, Dict, Any


# ---------------------------------------------------------------------------
# 1. Fake "Airtable API" - stands in for real HTTP calls in this demo.
#    In production this would be `requests.get(url, headers=auth_headers)`
#    against https://api.airtable.com/v0/{base_id}/{table_name}
# ---------------------------------------------------------------------------

FAKE_AIRTABLE_DB = {
    "Orders": [
        {"id": "rec001", "client": "Nordic Interiors", "amount": 4200, "status": "Shipped", "days_overdue": 0},
        {"id": "rec002", "client": "Alpine Living Co.", "amount": 1875, "status": "Pending", "days_overdue": 12},
        {"id": "rec003", "client": "Maison Verte", "amount": 6100, "status": "Pending", "days_overdue": 3},
        {"id": "rec004", "client": "Studio Lumen", "amount": 2950, "status": "Shipped", "days_overdue": 0},
        {"id": "rec005", "client": "Terra Textiles", "amount": 3400, "status": "Pending", "days_overdue": 21},
    ],
    "Invoices": [
        {"id": "inv001", "order_id": "rec001", "invoiced_amount": 4200, "paid": True},
        {"id": "inv002", "order_id": "rec003", "invoiced_amount": 18300, "paid": False},
        {"id": "inv003", "order_id": "rec004", "invoiced_amount": 2950, "paid": True},
    ],
}


def fake_airtable_request(table_name: str, offset: int = 0, page_size: int = 2):
    """
    Simulates a single paginated Airtable API call.
    Real Airtable responses include an `offset` token when there's another
    page; we mimic that here so the pagination loop below behaves the same
    way it would against the real API.
    """
    records = FAKE_AIRTABLE_DB.get(table_name, [])
    page = records[offset:offset + page_size]
    next_offset = offset + page_size if offset + page_size < len(records) else None
    time.sleep(0.05)  # pretend there's network latency
    return {"records": page, "offset": next_offset}


def fetch_all_records(table_name: str) -> List[Dict[str, Any]]:
    """
    Pulls every record from a table, paging through until Airtable stops
    returning an `offset`. This is the piece that's easy to get wrong if
    you only fetch the first 100 records and assume that's everything.
    """
    all_records = []
    offset = 0
    while True:
        response = fake_airtable_request(table_name, offset=offset)
        all_records.extend(response["records"])
        if response["offset"] is None:
            break
        offset = response["offset"]
    return all_records


# ---------------------------------------------------------------------------
# 2. Data integrity checks - this is where the real project caught a bug
#    that had inflated reported revenue by ~3x. Demonstrated here with
#    sample logic: flag revenue mismatches between Orders and Invoices.
# ---------------------------------------------------------------------------

@dataclass
class RevenueDiscrepancy:
    order_id: str
    client: str
    order_amount: float
    invoiced_amount: float
    difference: float


def find_revenue_discrepancies(orders: List[Dict], invoices: List[Dict]) -> List[RevenueDiscrepancy]:
    invoice_by_order = {inv["order_id"]: inv for inv in invoices}
    discrepancies = []
    for order in orders:
        invoice = invoice_by_order.get(order["id"])
        if invoice and invoice["invoiced_amount"] != order["amount"]:
            discrepancies.append(RevenueDiscrepancy(
                order_id=order["id"],
                client=order["client"],
                order_amount=order["amount"],
                invoiced_amount=invoice["invoiced_amount"],
                difference=invoice["invoiced_amount"] - order["amount"],
            ))
    return discrepancies


def find_overdue_orders(orders: List[Dict], threshold_days: int = 7) -> List[Dict]:
    """Surfaces orders that are overdue but might not be shown on any dashboard."""
    return [o for o in orders if o["status"] == "Pending" and o["days_overdue"] > threshold_days]


# ---------------------------------------------------------------------------
# 3. Export step - where Power BI actually picks up fresh data.
#    In production this could push to a database, a Power BI Push Dataset
#    via REST API, or (as here) a CSV file Power BI is scheduled to refresh
#    from automatically, replacing the old "manual export" step entirely.
# ---------------------------------------------------------------------------

def export_for_powerbi(orders: List[Dict], filename: str = "powerbi_orders_feed.csv"):
    fieldnames = ["id", "client", "amount", "status", "days_overdue"]
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(orders)
    print(f"Wrote {len(orders)} rows to {filename} for Power BI to refresh from.")


# ---------------------------------------------------------------------------
# Run the demo end-to-end
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Fetching Orders (paginated)...")
    orders = fetch_all_records("Orders")
    print(f"  -> {len(orders)} records pulled\n")

    print("Fetching Invoices (paginated)...")
    invoices = fetch_all_records("Invoices")
    print(f"  -> {len(invoices)} records pulled\n")

    print("Checking for revenue discrepancies (Orders vs Invoices)...")
    discrepancies = find_revenue_discrepancies(orders, invoices)
    for d in discrepancies:
        print(f"  ! {d.client}: order shows {d.order_amount}, invoice shows {d.invoiced_amount} "
              f"(diff: {d.difference:+})")
    if not discrepancies:
        print("  No discrepancies found in this sample.")
    print()

    print("Checking for overdue orders not likely surfaced on a dashboard...")
    overdue = find_overdue_orders(orders)
    for o in overdue:
        print(f"  ! {o['client']} — {o['days_overdue']} days overdue")
    print()

    export_for_powerbi(orders)
