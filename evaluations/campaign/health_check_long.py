import os, json, time, hashlib, subprocess
from collections import Counter

REPO = "/home/yaser/raphael-2.0-rbsv2r"
J = REPO + "/evaluations/campaign/rbs_v4_holdout.jsonl"
FREEZE = os.path.join(REPO, "evaluations/campaign/TERMINAL_VALIDATION_FREEZE.json")
COLLECTOR_SCRIPT = "scripts/run_rbs_v4_holdout_frozen.py"
PREV = "/tmp/holdout_health_prev.json"

def sha(path):
    if not os.path.exists(path): return "MISSING"
    return hashlib.sha256(open(path,"rb").read()).hexdigest()

def collector_procs():
    out = subprocess.run(["ps","-eo","pid,ppid,etime,%cpu,cmd"],
                         capture_output=True, text=True).stdout
    procs=[]
    for line in out.splitlines():
        if COLLECTOR_SCRIPT in line and "grep" not in line:
            procs.append(line.strip())
    return procs

def main():
    report = {"checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # 1. collector process
    procs = collector_procs()
    report["collector_procs"] = len(procs)
    report["proc_list"] = procs
    report["collector_3499_alive"] = any(p.split()[0]=="3499" for p in procs)

    # 2. rows
    rows=[]
    if os.path.exists(J):
        for line in open(J):
            line=line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except Exception: pass
    ok=[r for r in rows if "error" not in r]
    err=[r for r in rows if "error" in r]
    n=len(ok)
    report["valid_rows"]=n
    report["target_rows"]=1200
    report["error_rows"]=len(err)

    # 6. dup run_ids
    seen={}; dups=[]
    for r in ok:
        rid=r.get("run_id")
        if rid is None: continue
        if rid in seen: dups.append(rid)
        seen[rid]=True
    report["duplicate_run_ids"]=len(dups)

    # 4. infra / 3. frozen box
    n_infra=0
    models=Counter(); providers=Counter()
    arms=Counter(); fams=Counter()
    bad_seed=[]
    for r in ok:
        pf=r.get("provider_failures") or 0
        inf=r.get("infra_failures") or []
        if pf>0 or inf: n_infra+=1
        models[r.get("model_id")]+=1
        providers[r.get("provider")]+=1
        arms[r.get("config")]+=1
        fams[r.get("template")]+=1
        s=r.get("abs_seed")
        if not (2000 <= s < 10000): bad_seed.append(s)
    report["infra_failures"]=n_infra
    report["model_ids"]=dict(models)
    report["providers"]=dict(providers)
    report["arms"]=dict(arms)
    report["families"]=dict(fams)
    report["bad_seed_out_of_range"]=bad_seed
    model_identity_ok = (len(models)==0) or (set(models)=={"nvidia/llama-3.3-nemotron-super-49b-v1"})
    report["model_identity_ok"]=model_identity_ok

    # 7. freeze hashes unchanged
    if os.path.exists(FREEZE):
        fh=json.load(open(FREEZE)).get("files_sha256",{})
        changed=[]
        for rel,fr in fh.items():
            cur=sha(os.path.join(REPO,rel))
            if cur!=fr:
                changed.append((rel,fr,cur))
        report["freeze_hash_changed"]=changed
    else:
        report["freeze_hash_changed"]="FREEZE FILE MISSING"

    # 8. prev rows (monotonic)
    prev=0
    if os.path.exists(PREV):
        try: prev=json.load(open(PREV)).get("valid_rows",0)
        except Exception: pass
    report["prev_valid_rows"]=prev
    report["row_count_increased"]=(n>prev)
    report["row_count_advanced_this_check"]=max(0,n-prev)
    json.dump({"valid_rows":n,"ts":report["checked_at_utc"]}, open(PREV,"w"))

    print(json.dumps(report, indent=2))

    # gate
    print("---GATE---")
    fails=[]
    if len(procs)>1: fails.append("EXTRA COLLECTOR PROC(s): %d"%len(procs))
    if report["error_rows"]!=0: fails.append("ERROR ROWS=%d"%report["error_rows"])
    if report["duplicate_run_ids"]!=0: fails.append("DUP RUN IDS=%d"%report["duplicate_run_ids"])
    if n_infra!=0: fails.append("INFRA FAILURES=%d"%n_infra)
    if bad_seed: fails.append("SEED OUT OF RANGE=%s"%bad_seed)
    if not model_identity_ok: fails.append("MODEL IDENTITY WRONG")
    if isinstance(report["freeze_hash_changed"],list) and report["freeze_hash_changed"]: fails.append("FREEZE HASH CHANGED")
    if len(procs)==0 and n==0 and prev>0:
        fails.append("PROCESS DIED and no progress")
    if fails:
        print("STATUS: STOP-AND-CLASSIFY -> " + " | ".join(fails))
    else:
        print("STATUS: HEALTHY — continue passive monitoring. Perf sealed.")

main()