import json

SPACE = 'ws ::= | " " | "\\n" [ \\t]{0,20}'
COMPACT_SPACE = 'ws ::= | " "'
PRIMITIVES = {
    "string": r'"\"" char* "\"" ws',
    "number": r'"-"? ("0" | [1-9] [0-9]{0,15}) ("." [0-9]+)? ([eE] [-+]? [0-9]+)? ws',
    "integer": r'"-"? ("0" | [1-9] [0-9]{0,15}) ws',
    "boolean": r'("true" | "false") ws',
    "null": r'"null" ws',
}
CHAR = r'char ::= [^"\\\x7F\x00-\x1F] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4})'


def _lit(value):
    s = json.dumps(value, ensure_ascii=False)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '" ws'


class _Builder:
    def __init__(self):
        self.rules = {}

    def add(self, name, body):
        name = "".join(ch if ch.isascii() and (ch.isalnum() or ch == "-") else "-" for ch in name)
        base, i = name, 1
        while name in self.rules and self.rules[name] != body:
            name, i = f"{base}{i}", i + 1
        self.rules[name] = body
        return name

    def visit(self, schema, name):
        if schema is True or schema == {}:
            self._generic()
            return "value"
        if "const" in schema:
            return self.add(name, _lit(schema["const"]))
        if "enum" in schema:
            return self.add(name, " | ".join(_lit(v) for v in schema["enum"]))
        for key in ("anyOf", "oneOf"):
            if key in schema:
                alts = [self.visit(s, f"{name}-{i}") for i, s in enumerate(schema[key])]
                return self.add(name, " | ".join(alts))
        t = schema.get("type")
        if isinstance(t, list):
            return self.add(name, " | ".join(self.visit({**schema, "type": x}, f"{name}-{x}") for x in t))
        if t == "object" or "properties" in schema:
            props = schema.get("properties", {})
            if not props:
                self._generic()
                return "object"
            req = set(schema.get("required", []))
            items = [(f'{_lit(k)} ":" ws {self.visit(v, f"{name}-{k}")}', k in req) for k, v in props.items()]
            must = [i for i, r in items if r]
            may = [i for i, r in items if not r]
            if must:
                body = " ".join([must[0]] + [f'"," ws {i}' for i in must[1:]] + [f'("," ws {i})?' for i in may])
            else:
                body = "(" + " | ".join(" ".join([may[k]] + [f'("," ws {i})?' for i in may[k + 1:]]) for k in range(len(may))) + ")?"
            return self.add(name, f'"{{" ws {body} "}}" ws')
        if t == "array":
            item = self.visit(schema.get("items", {}), f"{name}-item")
            mx = schema.get("maxItems")
            rest = f'("," ws {item}){{0,{max(int(mx) - 1, 0)}}}' if mx else f'("," ws {item})*'
            return self.add(name, f'"[" ws ({item} {rest})? "]" ws')
        if t == "string" and schema.get("maxLength"):
            return self.add(name, f'"\\"" char{{0,{int(schema["maxLength"])}}} "\\"" ws')
        if t in PRIMITIVES:
            return self.add(t, PRIMITIVES[t])
        return self.visit(True, name)

    def _generic(self):
        self.rules.setdefault("value", 'object | array | string | number | boolean | null')
        self.rules.setdefault("object", r'"{" ws ( string ":" ws value ( "," ws string ":" ws value )* )? "}" ws')
        self.rules.setdefault("array", r'"[" ws ( value ( "," ws value )* )? "]" ws')
        for k, v in PRIMITIVES.items():
            self.rules.setdefault(k, v)


def schema_to_grammar(schema):
    b = _Builder()
    top = b.visit(schema, "root-value")
    space = COMPACT_SPACE if isinstance(schema, dict) and schema.get("x-compact") else SPACE
    lines = [f"root ::= {top}"] + [f"{k} ::= {v}" for k, v in b.rules.items()] + [space, CHAR]
    return "\n".join(lines) + "\n"
