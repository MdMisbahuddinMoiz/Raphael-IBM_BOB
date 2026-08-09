import os, sys, json, time
from collections import Counter

J = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/rbs_v4_holdout.jsonl"

def main():
    if not os.path.exists(J):
        print("NO JSONL YET"); return
    rows=[]
    for line in open(J):
        line=line.strip()
        if not line: continue
        try: rows.append(json.loads(line))
        except Exception: pass
    ok=[r for r in rows if "error" not in r]
    err=[r for r in rows if "error" in r]
    valid=[r for r in rows]
    # duplicate run_id check
    seen={}
    dups=[]
    for r in ok:
        rid=r.get("run_id")
        if rid is None: continue
        if rid in seen: dups.append(rid)
        seen[rid]=r
    # infra check
    n_infra=0; infra_rows=[]
    n_note=0
    for r in ok:
        pf=r.get("provider_failures") or 0
        inf=r.get("infra_failures") or []
        n_infra += (1 if (pf>0 or inf) else 0)
        if pf>0 or inf: infra_rows.append((r.get("config"),r.get("template"),r.get("seed"),pf,inf))
    # per-arm counts
    arm=Counter(r.get("config") for r in ok)
    fam=Counter(r.get("template") for r in ok)
    # model/provider
    models=Counter(r.get("model_id") for r in ok)
    # abs seed range
    bad_seed=[r.get("abs_seed") for r in ok if not (2000<= (r.get("abs_seed") or 0) <10000)]
    print("TOTAL rows:", len(rows), "| valid(non-error):", len(ok), "| error rows:", len(err))
    print("per-arm:", dict(arm))
    print("per-family:", dict(fam))
    print("models:", dict(models))
    print("dup_run_ids:", len(dups))
    print("infra rows (pfail>0 or infra_failures):", n_infra)
    for x in infra_rows[-5:]: print("   INFRA:", x)
    print("abs_seed_out_of_range:", len(bad_seed))
    if n_infra==0 and not dups and not bad_seed and len(ok)>0:
        print("HEALTH: CLEAN")
    else:
        print("HEALTH: !! review above !!")
    # rate
    if ok:
        ts=[r.get("timestamp") for r in ok if r.get("timestamp")]
        if len(ts)>=2:
            from datetime import datetime
            try:
                t0=datetime.strptime(ts[0],"%Y-%m-%dT%H:%M:%SZ")
                t1=datetime.strptime(ts[-1],"%Y-%m-%dT%H:%M:%SZ")
                dt=(t1-t0).total_seconds()
                rate=len(ok)/dt if dt>0 else 0
                eta = (1200-len(ok))/rate/3600 if rate>0 else float("inf")
                print(f"rows={len(ok)} over {dt:.0f}s -> {rate*60:.2f} rows/min | eta={eta:.1f}h")
            except Exception as e:
                print("rate calc skip:", e)

main()