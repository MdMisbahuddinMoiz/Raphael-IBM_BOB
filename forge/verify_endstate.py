"""Verify current conclusion_adapters.py is the intended Option A end-state. v2 — fixed extraction."""
import re
import subprocess
import sys

sys.path.insert(0, "src")
import arena.conclusion_adapters as ca

PATH = "src/arena/conclusion_adapters.py"
BAK = "src/arena/conclusion_adapters.py.bak"

# 1. Compile
r = subprocess.run([sys.executable, "-m", "py_compile", PATH], capture_output=True, text=True)
print("[1] compile:", "OK" if r.returncode == 0 else "FAIL\n" + r.stderr)

# 2. Runtime adapter mapping (authoritative)
a = ca.get_adapter("PROMPTED_AGENT")
print("[2] get_adapter('PROMPTED_AGENT') ->", type(a).__name__)

# 3. Key symbols via AST (precise, ignores docstrings/comments)
import ast
tree = ast.parse(open(PATH, encoding="utf-8").read())
defs = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        defs.setdefault(node.name, 0)
        defs[node.name] += 1
print("[3] symbol counts:")
for name in ["_parse_structured_conclusion", "_parse_fallback_heuristic",
             "_falsification_to_claims", "_defeater_to_claims",
             "LLMOnlyConclusionAdapter", "FullConclusionAdapter", "get_adapter"]:
    print(f"    {name}: {defs.get(name, 0)}")

# 4. Compare _falsification/_defeater bodies vs .bak using AST spans
bak_src = open(BAK, encoding="utf-8", errors="replace").read()
try:
    bak_tree = ast.parse(bak_src)
    bak_ok = True
except SyntaxError as e:
    bak_ok = False
    print("[4] .bak parse:", f"FAILED ({e})")

def ast_source_map(text, tree_):
    """Return {name: source_segment} for top-level defs, via line numbers."""
    lines = text.splitlines(keepends=True)
    out = {}
    for node in tree_.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            seg = "".join(lines[node.lineno - 1:node.end_lineno])
            out[node.name] = seg
    return out

cur_map = ast_source_map(open(PATH, encoding="utf-8").read(), tree)
if bak_ok:
    bak_map = ast_source_map(bak_src, bak_tree)
    for name in ["_falsification_to_claims", "_defeater_to_claims", "_evidence_to_llm_claims",
                 "_compute_decision"]:
        cur_seg = cur_map.get(name, "")
        bak_seg = bak_map.get(name, "")
        cur_n = "\n".join(l.rstrip() for l in cur_seg.splitlines())
        bak_n = "\n".join(l.rstrip() for l in bak_seg.splitlines())
        same = cur_n == bak_n
        print(f"[4] {name}: {'IDENTICAL to .bak' if same else 'DIFFERS from .bak'}")
        if not same:
            import difflib
            print("      diff lines (old=.bak, new=current):")
            for d in list(difflib.unified_diff(bak_n.splitlines(), cur_n.splitlines(), lineterm=""))[:16]:
                print("      ", d)

# 5. Fallback + structured parser presence (runtime)
print("[5] fallback callable:", callable(getattr(ca, "_parse_fallback_heuristic", None)))
print("[5] structured parser callable:", callable(getattr(ca, "_parse_structured_conclusion", None)))

# 6. Factory mapping contents (runtime introspection)
import inspect
src_txt = inspect.getsource(ca.get_adapter)
m = re.search(r"mapping = \{(.*?)\n    \}", src_txt, re.S)
if m:
    keys = re.findall(r'"([A-Z_]+)"\s*:', m.group(1))
    print("[6] factory keys:", keys)
