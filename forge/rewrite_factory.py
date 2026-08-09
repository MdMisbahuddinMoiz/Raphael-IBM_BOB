# Rewrite the end of the file cleanly
import re

with open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py', 'r') as f:
    content = f.read()

# Remove any null bytes
content = content.replace('\x00', '')

# Find the adapter factory section and rewrite it cleanly
factory_start = content.find('# ── Adapter Factory ────────────────────────────────────────────')
if factory_start == -1:
    print("ERROR: Could not find adapter factory section")
    exit(1)

# Keep everything before the factory section
before_factory = content[:factory_start]

# New factory section
new_factory = '''# ── Adapter Factory ────────────────────────────────────────────

def get_adapter(config_id: str):
    """Return the appropriate adapter for the given config."""
    mapping = {
        "FULL_RAPHAEL": FullConclusionAdapter,
        "NO_HYPOTHESIS": NoHypothesisConclusionAdapter,
        "NO_WORLD_MODEL": NoWorldModelConclusionAdapter,
        "NO_PLANNER": NoPlannerConclusionAdapter,
        "NO_FALSIFICATION": NoFalsificationConclusionAdapter,
        "NO_DEFEATER": NoDefeaterConclusionAdapter,
        "NO_LLM": NoLLMConclusionAdapter,
        "LLM_ONLY": LLMOnlyConclusionAdapter,
        "SCRIPTED_BASELINE": ScriptedConclusionAdapter,
    }
    cls = mapping.get(config_id, FullConclusionAdapter)
    return cls()
'''

new_content = before_factory + new_factory

# Write back
with open('/home/yaser/raphael-2.0-rbsv2r/src/arena/conclusion_adapters.py', 'w') as f:
    f.write(new_content)

print("File rewritten successfully")