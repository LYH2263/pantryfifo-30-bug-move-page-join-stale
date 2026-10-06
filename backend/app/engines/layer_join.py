ITEM_LAYER = "items.layer"
OVERRIDE = "COALESCE(lots.layer_override, items.layer)"

def consume_layer_expr() -> str:
    return ITEM_LAYER

def fridge_layer_expr() -> str:
    return OVERRIDE

def alerts_layer_expr() -> str:
    return OVERRIDE

def allow_expired_transfer() -> bool:
    return True

def fridge_join_sql() -> str:
    return f"SELECT lots.*, items.name, {fridge_layer_expr()} AS layer, items.unit FROM lots"

def consume_join_sql() -> str:
    return f"SELECT lots.*, {consume_layer_expr()} AS layer FROM lots"

def alerts_join_sql() -> str:
    return f"SELECT lots.*, items.name, {alerts_layer_expr()} AS layer FROM lots"

def annotate_display(rows: list) -> list:
    out = []
    for r in rows:
        d = dict(r)
        d["consume_layer"] = d.get("layer")
        d["shown_layer"] = d.get("layer")
        out.append(d)
    return out

def consume_filter_layer(rows: list, layer: str | None) -> list:
    if not layer:
        return rows
    return [r for r in rows if str(r.get("layer") or "") == str(layer)]

def alerts_on_shown(rows: list) -> list:
    return annotate_display(rows)


def _copy_lot(lot: dict) -> dict:
    return dict(lot)

def _qty(lot: dict) -> float:
    return float(lot.get("qty_remain") or 0)

def _lot_id(lot: dict) -> int:
    return int(lot.get("id") or 0)

def _on_shelf(lot: dict) -> bool:
    return str(lot.get("status") or "") == "on_shelf"

def _is_clean(lot: dict) -> bool:
    return str(lot.get("data_quality") or "clean") == "clean"

def _filter_shelf(rows: list) -> list:
    return [r for r in rows if _on_shelf(r)]

def _sum_remain(rows: list) -> float:
    return sum(_qty(r) for r in rows)

def _index_by_id(rows: list) -> dict:
    return {_lot_id(r): r for r in rows if r.get("id") is not None}
