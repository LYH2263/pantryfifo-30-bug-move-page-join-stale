"""层位归属的唯一定义点。

所有「这批在哪个层」的判定——总表过滤（/fridge）、分层页（/fridge?layer=）、
按层 FEFO 扣减（/consume）、紧急条（/alerts）——都必须取
effective_layer_expr() 这同一个表达式：批级覆盖优先，缺省回落品项默认层。

转层只写 lots.layer_override，于是这批在任何视图里同时换层，
不会出现分层页已在中层、总表/扣减还按下层点名的分裂。
禁止再各自另写 items.layer 或 COALESCE(...) 字面量。
"""

EFFECTIVE_LAYER = "COALESCE(lots.layer_override, items.layer)"


def effective_layer_expr() -> str:
    return EFFECTIVE_LAYER


# 语义别名：三处视图名不同，但取的是同一个覆盖，不允许分叉。
def fridge_layer_expr() -> str:
    return EFFECTIVE_LAYER


def consume_layer_expr() -> str:
    return EFFECTIVE_LAYER


def alerts_layer_expr() -> str:
    return EFFECTIVE_LAYER
