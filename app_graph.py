

def _link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _fixed(graph, v):
    if isinstance(v, bool):
        return v
    if _link(v) and graph.get(v[0], {}).get("class_type") == "PrimitiveBoolean":
        b = graph[v[0]]["inputs"].get("value")
        return b if isinstance(b, bool) else None
    return None


def without_unused(graph, known, is_output):
    if all(nd["class_type"] in known for nd in graph.values()):
        return graph
    pick = {}
    for k, nd in graph.items():
        if nd["class_type"] == "ComfySwitchNode":
            on = _fixed(graph, nd["inputs"].get("switch"))
            src = None if on is None else nd["inputs"].get("on_true" if on else "on_false")
            if src is not None:
                pick[k] = src

    def through(v):
        seen = set()
        while _link(v) and v[0] in pick and v[0] not in seen:
            seen.add(v[0])
            v = pick[v[0]]
        return v

    for k, nd in graph.items():
        if k not in pick:
            for a, v in nd["inputs"].items():
                nd["inputs"][a] = through(v)
    for k in pick:
        del graph[k]
    keep = set()
    todo = [k for k, nd in graph.items() if nd["class_type"] in known and is_output(nd["class_type"])]
    while todo:
        k = todo.pop()
        if k in keep or k not in graph:
            continue
        keep.add(k)
        todo += [v[0] for v in graph[k]["inputs"].values() if _link(v)]
    for k in [k for k in graph if k not in keep]:
        del graph[k]
    return graph
