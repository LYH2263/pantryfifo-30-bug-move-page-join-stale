"""转层后层位口径一致性：总表过滤、分层页、按层扣减、紧急条、收走名单
必须认同一个有效层 COALESCE(lots.layer_override, items.layer)，
过期资格必须与 is_expired 同一谓词。
"""
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

FUTURE = "2099-01-01"
FUTURE2 = "2099-06-01"
PAST = "2000-01-01"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.main import app
    with TestClient(app) as c:
        # 清掉 seed 的示例批次，只留品项目录，断言不被无关批次干扰
        conn = sqlite3.connect(tmp_path / "pantryfifo.db")
        conn.execute("DELETE FROM lots")
        conn.commit()
        conn.close()
        yield c


def inbound(client, item_id, expiry, qty=1):
    r = client.post("/api/lots", json={"item_id": item_id, "qty": qty, "expiry": expiry})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ids_in(client, layer):
    return [x["id"] for x in client.get(f"/api/fridge?layer={layer}").json()]


def layers_map(client):
    return {row["id"]: row["layer"] for row in client.get("/api/fridge").json()}


def qty(client, lot_id):
    for row in client.get("/api/fridge").json():
        if row["id"] == lot_id:
            return row["qty_remain"]
    return None


def test_transfer_single_lot_only_in_target_layer(client):
    moved = inbound(client, 3, FUTURE)          # 冻饺，默认 lower
    sibling = inbound(client, 3, FUTURE2)       # 同品项另一批

    assert layers_map(client)[moved] == "lower"

    r = client.post("/api/transfer",
                    json={"lot_id": moved, "to_layer": "mid", "from_layer": "lower"})
    assert r.status_code == 200, r.text

    # 全层总表里该身份只出现一次，且挂在中层
    full = client.get("/api/fridge").json()
    hits = [row for row in full if row["id"] == moved]
    assert len(hits) == 1 and hits[0]["layer"] == "mid"
    # 过滤视图：只在中层看见，下层不再出现同一身份
    assert moved in ids_in(client, "mid")
    assert moved not in ids_in(client, "lower")
    # 同品项其余批次不被一起改层
    assert layers_map(client)[sibling] == "lower"
    # 转层不动余量
    assert qty(client, moved) == 1


def test_consume_layer_filter_follows_override(client):
    early = inbound(client, 3, FUTURE)           # 先到期
    late = inbound(client, 3, FUTURE2)           # 后到期
    r = client.post("/api/transfer",
                    json={"lot_id": early, "to_layer": "mid", "from_layer": "lower"})
    assert r.status_code == 200, r.text

    # 按下层扣：先到期那批已转到中层，不能再被当下层库存 FEFO 扣走
    r = client.post("/api/consume", json={"item_id": 3, "qty": 1, "layer": "lower"})
    assert r.status_code == 200, r.text
    assert [d["lot_id"] for d in r.json()["deductions"]] == [late]

    # 按中层扣：才能扣到转走的那批
    r = client.post("/api/consume", json={"item_id": 3, "qty": 1, "layer": "mid"})
    assert r.status_code == 200, r.text
    assert [d["lot_id"] for d in r.json()["deductions"]] == [early]


def test_consume_without_layer_still_fefo_across_layers(client):
    early = inbound(client, 3, FUTURE)
    inbound(client, 3, FUTURE2)
    client.post("/api/transfer",
                json={"lot_id": early, "to_layer": "mid", "from_layer": "lower"})
    r = client.post("/api/consume", json={"item_id": 3, "qty": 1})
    assert r.status_code == 200, r.text
    # 不指定层时跨层 FEFO：最早到期（已在中层）先扣
    assert [d["lot_id"] for d in r.json()["deductions"]] == [early]


def test_expired_lot_cannot_transfer_and_state_untouched(client):
    lid = inbound(client, 3, PAST)

    r = client.post("/api/transfer",
                    json={"lot_id": lid, "to_layer": "mid", "from_layer": "lower"})
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "expired"

    # 失败路径：层位与余量一起留在原状，没有 mid/lower 双挂，也没改余量
    assert layers_map(client).get(lid) == "lower"
    assert qty(client, lid) == 1
    assert lid not in ids_in(client, "mid")


def test_expired_eligibility_same_as_alerts_and_sweep(client):
    lid = inbound(client, 3, PAST)  # 已过期仍在架，下层

    # 紧急条按同一谓词报过期，层位取覆盖
    alerts = client.get("/api/alerts").json()
    a = [x for x in alerts if x["id"] == lid]
    assert len(a) == 1 and a[0]["level"] == "expired" and a[0]["layer"] == "lower"

    # 收走后：层页与紧急条同时消失（同一资格，不各报各的）
    r = client.post("/api/expire-sweep")
    assert lid in r.json()["expired_ids"]
    assert lid not in layers_map(client)
    assert lid not in [x["id"] for x in client.get("/api/alerts").json()]


def test_expired_lot_on_mid_reported_as_mid_everywhere(client, tmp_path):
    # 构造「已过期且已挂在中层」的批（历史转层后到期）：
    # 紧急条必须按中层过期集合报，收走后中层页同步消失，不得仍按下层点名。
    lid = inbound(client, 3, PAST)
    conn = sqlite3.connect(tmp_path / "pantryfifo.db")
    conn.execute("UPDATE lots SET layer_override='mid' WHERE id=?", (lid,))
    conn.commit()
    conn.close()

    assert lid in ids_in(client, "mid")
    assert lid not in ids_in(client, "lower")
    a = [x for x in client.get("/api/alerts").json() if x["id"] == lid]
    assert len(a) == 1 and a[0]["level"] == "expired" and a[0]["layer"] == "mid"

    # 已过期批不允许再转层
    r = client.post("/api/transfer",
                    json={"lot_id": lid, "to_layer": "upper", "from_layer": "mid"})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "expired"

    client.post("/api/expire-sweep")
    assert lid not in ids_in(client, "mid")
    assert lid not in [x["id"] for x in client.get("/api/alerts").json()]


def test_from_layer_guard_and_bad_requests(client):
    lid = inbound(client, 3, FUTURE)
    assert client.post("/api/transfer",
                       json={"lot_id": lid, "to_layer": "sideways",
                             "from_layer": "lower"}).status_code == 400
    assert client.post("/api/transfer",
                       json={"lot_id": 99999, "to_layer": "mid"}).status_code == 404

    assert client.post("/api/transfer",
                       json={"lot_id": lid, "to_layer": "mid",
                             "from_layer": "lower"}).status_code == 200
    # 守卫还按下层点名 → 服务端已是中层，拒绝而不是再改一次
    r = client.post("/api/transfer",
                    json={"lot_id": lid, "to_layer": "upper", "from_layer": "lower"})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "layer_changed"
    # 用最新层位点名、转到同一层 → same_layer
    r = client.post("/api/transfer",
                    json={"lot_id": lid, "to_layer": "mid", "from_layer": "mid"})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "same_layer"
    assert layers_map(client)[lid] == "mid"


def test_concurrent_transfer_single_winner(tmp_path, monkeypatch):
    # 两个连接同时把同一批转走：BEGIN IMMEDIATE 串行化，后到者读到已提交的
    # 新层位，被 from_layer 守卫拒绝——不会双挂，也不会层改了余量没跟上。
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import seed
    from app.db import connect
    from app.engines.layer_join import EFFECTIVE_LAYER
    from app.modules.temp_zone import transfer_lot
    seed.init_db()

    c = connect()
    lid = c.execute(
        "INSERT INTO lots(item_id,qty_in,qty_remain,expiry,status,data_quality) "
        "VALUES (3,1,1,?,'on_shelf','clean')", (FUTURE,)).lastrowid
    c.commit()
    c.close()

    out = []

    def fire(to):
        cc = connect()
        try:
            out.append(transfer_lot(cc, lid, to, "lower"))
        finally:
            cc.close()

    t1 = threading.Thread(target=fire, args=("mid",))
    t2 = threading.Thread(target=fire, args=("upper",))
    t1.start(); t2.start(); t1.join(); t2.join()

    ok = [r for r in out if r["ok"]]
    rejected = [r for r in out if not r["ok"]]
    assert len(ok) == 1 and len(rejected) == 1
    assert rejected[0]["reason"] == "layer_changed"

    c = connect()
    row = c.execute(
        f"SELECT {EFFECTIVE_LAYER} AS layer, qty_remain FROM lots "
        "JOIN items ON items.id=lots.item_id WHERE lots.id=?", (lid,)).fetchone()
    c.close()
    assert row["layer"] == ok[0]["to_layer"]
    assert row["qty_remain"] == 1
