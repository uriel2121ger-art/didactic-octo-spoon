from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from pos_core import POSCore
from server import auth

core = POSCore()
core.ensure_schema()
router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(current_user: dict = Depends(auth.get_current_dashboard_user)):
    today = datetime.utcnow().date().isoformat()
    summary = core.sales_summary(date_from=today, date_to=today)
    layaways = [dict(row) for row in core.list_layaways(status="pendiente")]
    credit_accounts = core.list_credit_accounts()
    branch_row = core.get_branch(core.get_active_branch())
    return {
        "ventas_hoy": summary.get("total", 0.0),
        "tickets_hoy": summary.get("sales_count", 0),
        "apartados_hoy": len(layaways),
        "credito_clientes": len(credit_accounts),
        "total_credito": sum(float(c.get("credit_balance", 0.0)) for c in credit_accounts),
        "branch": dict(branch_row) if branch_row else None,
    }


@router.get("/dashboard/graph/sales")
def dashboard_sales_graph(current_user: dict = Depends(auth.get_current_dashboard_user)):
    labels: list[str] = []
    values: list[float] = []
    today = datetime.utcnow().date()
    start = today - timedelta(days=6)
    rows = core.daily_sales(date_from=start.isoformat(), date_to=today.isoformat())
    for row in rows:
        labels.append(row["day"])
        values.append(float(row["total"] or 0.0))
    return {"labels": labels, "values": values}


@router.get("/dashboard/alerts")
def dashboard_alerts(current_user: dict = Depends(auth.get_current_dashboard_user)):
    alerts: list[dict] = []
    inventory_rows = [dict(r) for r in core.list_inventory(core.get_active_branch())]
    low_stock = [r for r in inventory_rows if float(r.get("stock", 0)) <= float(r.get("min_stock", 0))]
    if low_stock:
        alerts.append({"type": "stock", "message": f"{len(low_stock)} productos con stock bajo"})
    credit = core.list_credit_accounts()
    if credit:
        alerts.append({"type": "credit", "message": f"{len(credit)} clientes con saldo"})
    layaways = [dict(row) for row in core.list_layaways(status="pendiente")]
    overdue = [la for la in layaways if la.get("display_status") == "vencido"]
    if overdue:
        alerts.append({"type": "layaway", "message": f"{len(overdue)} apartados vencidos"})
    return {"alerts": alerts}
