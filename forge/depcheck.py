import importlib, sys

mods = ["torch","transformers","numpy","pandas","requests","aiohttp","sqlalchemy",
        "pydantic","yaml","click","rich","psutil","docker","paramiko","cryptography",
        "fastapi","uvicorn","httpx","mcp","dns","neo4j","winrm","openai",
        "pytest","pytest_asyncio"]
missing = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        missing.append(f"{m}: {type(e).__name__}")
print("PYTHON:", sys.version.split()[0])
print("IMPORT CHECK:", "ALL OK" if not missing else "MISSING -> " + "; ".join(missing))