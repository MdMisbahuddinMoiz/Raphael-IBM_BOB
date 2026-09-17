import json, os, subprocess, sys, hashlib
sys.path.insert(0, "/home/moiz/raphael-2.0-rbsv2r")
from raphael_ibm_bob.isolation_substrate import (SandboxSpec, ProviderRef, FixtureRef,
                                                 build_bwrap_argv, NODE_RUNTIME)
from raphael_ibm_bob.seccomp_policy import build_policy
REPO="/home/moiz/raphael-2.0-rbsv2r"; G2="/tmp/raphael_g2"
OUT=REPO+"/docs/integration/phase-2c-m1"; os.makedirs(OUT, exist_ok=True)
JS=r'''
const fs=require("fs"); const R={};
function t(id,fn){ try { const v=fn(); R[id]={ok:true, value:String(v).slice(0,120)}; }
  catch(e){ R[id]={ok:false, code:e.code||null, errno:(e.errno===undefined?null:e.errno)}; } }
t("fixture_dotdot_list",()=>fs.readdirSync("/fixture/../..").join(","));
t("cgroup_read",()=>fs.readdirSync("/sys/fs/cgroup").join(","));
t("cgroup_write",()=>{fs.writeFileSync("/sys/fs/cgroup/cgroup.procs","1");return "WROTE";});
t("dev_list",()=>fs.readdirSync("/dev").join(","));
for (const d of ["core","fuse","pts","shm","tty","null","zero","urandom","random","full","stdin","fd"])
  t("dev_"+d,()=>{const s=fs.lstatSync("/dev/"+d);return (s.isSymbolicLink()?"link":s.isCharacterDevice()?"char":s.isDirectory()?"dir":"other")+" "+(s.isSymbolicLink()?fs.readlinkSync("/dev/"+d):"");});
t("dev_core_read",()=>{const b=Buffer.alloc(1);const fd=fs.openSync("/dev/core","r");try{fs.readSync(fd,b,0,1,0);}finally{fs.closeSync(fd);}return "READ_OK";});
t("dev_mem_read",()=>{const b=Buffer.alloc(1);const fd=fs.openSync("/dev/mem","r");try{fs.readSync(fd,b,0,1,0);}finally{fs.closeSync(fd);}return "READ_OK";});
process.stdout.write("M1B "+JSON.stringify(R));
'''
spec=SandboxSpec(provider=ProviderRef(root="/home/moiz/audit-repos/T3MP3ST",
      node_modules="/home/moiz/audit-repos/T3MP3ST/node_modules"),
      fixture=FixtureRef(root=REPO+"/fixtures/c1a_proof",
      path=REPO+"/fixtures/c1a_proof/raphael_c1a_fixture.txt",
      sha256="c033fda6e893ed965de8496ad170628d33ce69817c6ad05bbb63bcb5e1010bd1"))
argv=list(build_bwrap_argv(spec,seccomp_fd=3)); argv=argv[:-2]+[NODE_RUNTIME,"-e",JS]
build_policy(G2+"/policy.bpf")
fd=os.open(G2+"/policy.bpf",os.O_RDONLY); os.dup2(fd,3)
r=subprocess.run(argv,capture_output=True,text=True,pass_fds=(3,),timeout=120)
B=json.loads(r.stdout.split("M1B ",1)[1]) if "M1B " in r.stdout else {}
raw=json.load(open(G2+"/out/m1_evidence_raw.json")); P=raw["probe"]; F=raw["freeze"]
recs=[]; fails=[]
def rec(pid,expected,actual,ok,ev):
    recs.append({"probe_id":pid,"status":"PASS" if ok else "FAIL","expected":expected,"actual":actual,"evidence":ev})
    if not ok: fails.append(pid)
def all_enoent(d): return all(v=="ENOENT" for v in d.values())
rec("M1-P1","host paths not visible",P["p1"],all_enoent(P["p1"]),json.dumps(P["p1"]))
for k in ("p2_provider_dotdot","p2_node_dotdot","p2_normalized"):
    rec("M1-P2/"+k,"traversal denied (ENOENT)",P[k],not P[k]["ok"],json.dumps(P[k]))
rec("M1-P2/fixture_dotdot_list","traversal denied",B.get("fixture_dotdot_list"),
    not B.get("fixture_dotdot_list",{}).get("ok",True),json.dumps(B.get("fixture_dotdot_list")))
rec("M1-P3/proc_root_etc","read via /proc/self/root denied",P["p3_proc_root_etc"],not P["p3_proc_root_etc"]["ok"],json.dumps(P["p3_proc_root_etc"]))
rec("M1-P3/symlink_targets","readlink targets contained",P["p3_proc_exe"],
    P["p3_proc_exe"].get("value")=="/usr/bin/node",json.dumps([P["p3_proc_exe"],P["p3_proc_root"],P["p3_proc_cwd"]]))
for k in ("p4_provider_write","p4_node_modules_write","p4_node_write","p4_lib_write","p4_provider_unlink","p4_provider_mkdir"):
    rec("M1-P4/"+k,"write/unlink/mkdir denied",P[k],not P[k]["ok"],json.dumps(P[k]))
rec("M1-P5","fixture visible+ro; write/rename denied",
    {"exists":P["p5"]["fixture_exists"],"size":P["p5"]["fixture_read_bytes"],"write":P["p5_fixture_write"],"rename":P["p5_fixture_rename"]},
    P["p5"]["fixture_exists"]=="PRESENT" and not P["p5_fixture_write"]["ok"] and not P["p5_fixture_rename"]["ok"],
    json.dumps(P["p5"])+json.dumps(P["p5_fixture_write"])+json.dumps(P["p5_fixture_rename"]))
for pid,key in (("M1-P6","p6"),("M1-P7","p7"),("M1-P8","p8")):
    rec(pid,"host paths not visible",P[key],all_enoent(P[key]),json.dumps(P[key]))
sens=["core","mem","kmem","kmsg","console","sda","nvme0n1","fuse","pts"]
devs={k:B.get("dev_"+k) for k in sens}
present=[k for k,v in devs.items() if v and v.get("ok")]
readable=[k for k in ("core","mem") if B.get("dev_"+k+"_read",{}).get("ok")]
rec("M1-P9","only minimal /dev; raw/control devices absent or unreadable",
    {"list":B.get("dev_list"),"sensitive":devs,"readable":readable,"core_read":B.get("dev_core_read")},
    not readable, json.dumps({"sensitive":devs,"readable":readable,"list":B.get("dev_list")}))
p10=P["p10"]
rec("M1-P10","uid/gid 65534, caps 0, NNP=1, seccomp active",p10,
    p10["uid"]==65534 and p10["euid"]==65534 and p10["CapEff"]=="0000000000000000"
    and p10["NoNewPrivs"]=="1" and p10["Seccomp"] in ("2","1"),json.dumps(p10))
HN=raw["host_ns"]; diff={n:(P["p11"][n]!=HN[n]) for n in HN}
rec("M1-P11","namespaces differ from host",{"differ":diff},all(diff.values()),json.dumps({"s":P["p11"],"h":HN}))
p12=P["p12"]
rec("M1-P12","pidns isolated (pid1=bwrap, host pids absent)",p12,
    p12["pid1_cmdline"].startswith("bwrap ") and p12["proc_host_high"]=="ENOENT",json.dumps(p12))
p13=P["p13"]
rec("M1-P13","fork-like denied; thread clone allowed",p13,
    "DENIED" in p13["fork_like"] and str(p13["thread_pool"]).startswith("OK"),json.dumps(p13))
p14={k:P[k] for k in ("p14_setuid0","p14_setgid0","p14_setgroups") if k in P}
rec("M1-P14","identity changes denied",p14,all(not v["ok"] for v in p14.values()),json.dumps(p14))
rec("M1-P15","cgroupfs absent/unwritable; no upward escape",
    {"sys":P["p15_sys_exists"],"read":B.get("cgroup_read"),"write":B.get("cgroup_write")},
    P["p15_sys_exists"]=="ENOENT" and not B.get("cgroup_read",{}).get("ok",True)
    and not B.get("cgroup_write",{}).get("ok",True),
    json.dumps({"sys":P["p15_sys_exists"],"read":B.get("cgroup_read"),"write":B.get("cgroup_write")}))
p16=P["p16"]; rec("M1-P16","no child process can be created",p16,"DENIED" in p16["spawn"],json.dumps(p16))
doc={"artifact":"phase-2c-m1-evidence","stage":"M1","freeze":F,"host_ns":HN,"rc":raw["rc"],
     "total":len(recs),"pass":sum(1 for r in recs if r["status"]=="PASS"),
     "fail":sum(1 for r in recs if r["status"]=="FAIL"),"fails":fails,"records":recs,
     "observations":{"getdents64":"denied (readdir -> EPERM); a containment-positive",
       "seccomp":"active inside sandbox (Seccomp: 2)","scratch":"NO_SCRATCH (no writable fs)",
       "dev_sensitive_present":present,"dev_raw_readable":readable,
       "p15_read_raw":B.get("cgroup_read"),"p9_dev_note":"/dev/core is a bwrap minimal-dev symlink; read attempted and recorded"},
     "readdir_denied_probes":["M1-P2/fixture_dotdot_list","M1-P9/dev_list","M1-P15/cgroup_read"]}
open(OUT+"/m1-evidence.json","w").write(json.dumps(doc,indent=2)+"\n")
print("total",doc["total"],"pass",doc["pass"],"fail",doc["fail"],"fails",fails)
print("devs:",json.dumps(devs)); print("core_read:",B.get("dev_core_read"),"mem_read:",B.get("dev_mem_read"))
print("cgroup_read:",B.get("cgroup_read"),"cgroup_write:",B.get("cgroup_write"))
print("fixture_dotdot_list:",B.get("fixture_dotdot_list"))
print("sha256:",hashlib.sha256(open(OUT+"/m1-evidence.json","rb").read()).hexdigest())
