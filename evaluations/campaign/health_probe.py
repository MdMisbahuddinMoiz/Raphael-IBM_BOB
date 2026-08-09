import sys, os, time
_R="/home/yaser/raphael-2.0-rbsv2r"
sys.path.insert(0, os.path.join(_R,"src"))
os.chdir(_R)

def _load_dotenv(path):
    if not os.path.exists(path): return 0
    n=0
    with open(path) as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,_,v=line.partition("="); k=k.strip()
            if k and k not in os.environ:
                os.environ[k]=v.strip(); n+=1
    return n
print("loaded env keys:", _load_dotenv(os.path.join(_R,".env")))

from arena.ablation_runner import AblationRunner
from arena.ablation import ABLATION_PRESETS
from arena.templates import TEMPLATE_REGISTRY, ScenarioSplit

# Health probe: 1 network arm (FULL) + 1 hermetic control (SCRIPTED), seed 0, family[0]
cases=[("FULL_RAPHAEL","known-observable",0),("SCRIPTED_BASELINE","known-observable",0)]
for config_id, fam, seed in cases:
    template=TEMPLATE_REGISTRY[fam]
    runner=AblationRunner(template=template, config=ABLATION_PRESETS[config_id],
                          seed=seed, split="holdout")
    t0=time.time()
    m=runner.run()
    dt=time.time()-t0
    d=m.to_dict()
    svc=getattr(runner,"_llm_service",None)
    print("RESULT", config_id, "elapsed=%.1fs"%dt,
          "pfail=",d.get("provider_failures"),
          "mfail=",d.get("model_failures"),
          "infra=",d.get("infra_failures"),
          "disp=",d.get("actions_dispatched"),
          "iter=",d.get("iterations_used"),
          "llm_calls=",d.get("llm_calls"),
          "status=", getattr(svc,"final_provider_status",None) if svc else None,
          "failclass=", getattr(svc,"failure_class",None) if svc else None)