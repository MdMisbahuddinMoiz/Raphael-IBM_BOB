import json, os, re, subprocess, sys, hashlib, time, signal
sys.path.insert(0, "/home/moiz/raphael-2.0-rbsv2r")
from raphael_ibm_bob.isolation_substrate import (SandboxSpec, ProviderRef, FixtureRef,
                                                 build_bwrap_argv, NODE_RUNTIME, SCRATCH_MODE,
                                                 node_runtime_closure, PROXY_ENV_VARS)
from raphael_ibm_bob.seccomp_policy import build_policy
REPO="/home/moiz/raphael-2.0-rbsv2r"; G2="/tmp/raphael_g2"
OUT=REPO+"/docs/integration/phase-2c-m2"; os.makedirs(OUT, exist_ok=True)
os.makedirs(G2+"/out/st4", exist_ok=True)
MARK="RAPHAEL_M2_MARKER"
JS=r'''
const fs=require("fs"); const MARK="RAPHAEL_M2_MARKER";
function rd(p){try{return fs.readFileSync(p,"utf8")}catch(e){return "ERR:"+e.code}}
const info={dev:rd("/proc/net/dev"),route:rd("/proc/net/route"),ipv6:rd("/proc/net/ipv6_route"),
  resolv:(()=>{try{fs.accessSync("/etc/resolv.conf");return "PRESENT"}catch(e){return e.code}})(),
  proxy:Object.keys(process.env).filter(k=>/proxy/i.test(k)).sort(),
  netns:fs.readlinkSync("/proc/self/ns/net"), pid:process.pid};
process.stdout.write("M2INFO "+JSON.stringify(info)+"\n");
let ticks=0;
const iv=setInterval(()=>{
  ticks++;
  try{ const s=require("net").connect({host:"127.0.0.1",port:9}); s.on("error",()=>{}); }catch(e){}
  try{ const s=require("net").connect({host:"192.0.2.1",port:80}); s.on("error",()=>{}); }catch(e){}
  try{ const s=require("net").connect({host:"::1",port:9}); s.on("error",()=>{}); }catch(e){}
  try{ const d=require("dgram").createSocket("udp4"); d.on("error",()=>{}); d.send(Buffer.from("x"),9,"127.0.0.1",()=>{}); }catch(e){}
  try{ const srv=require("net").createServer(); srv.on("error",()=>{}); srv.listen(0,"127.0.0.1",()=>{}); }catch(e){}
}, 2000);
setTimeout(()=>{ clearInterval(iv); process.stdout.write("M2DONE "+ticks+"\n"); }, 18000);
'''
spec=SandboxSpec(provider=ProviderRef(root="/home/moiz/audit-repos/T3MP3ST",
      node_modules="/home/moiz/audit-repos/T3MP3ST/node_modules"),
      fixture=FixtureRef(root=REPO+"/fixtures/c1a_proof",
      path=REPO+"/fixtures/c1a_proof/raphael_c1a_fixture.txt",
      sha256="c033fda6e893ed965de8496ad170628d33ce69817c6ad05bbb63bcb5e1010bd1"))
base=list(build_bwrap_argv(spec,seccomp_fd=3)); argv=base[:-2]+[NODE_RUNTIME,"-e",JS]
d=build_policy(G2+"/policy.bpf")
freeze={"bpf_sha256":d.bpf_sha256,
 "allowlist_sha256":hashlib.sha256(open(REPO+"/docs/integration/phase-2c-g2/curated-allowlist.json","rb").read()).hexdigest(),
 "builder_argv_len":len(base),"scratch_mode":SCRATCH_MODE,"closure_paths":len(node_runtime_closure().all_paths()),
 "uid_gid":[base[base.index("--uid")+1],base[base.index("--gid")+1]],"unshare_net":("--unshare-net" in base),
 "seccomp_fd":base[base.index("--seccomp")+1],
 "unsetenv":[base[i+1] for i,t in enumerate(base) if t=="--unsetenv"],
 "proxy_vars":list(PROXY_ENV_VARS)}
res={"freeze":freeze,"assertions":{}, "trace":{}}
fd=os.open(G2+"/policy.bpf",os.O_RDONLY); os.dup2(fd,3); os.close(fd)
p=subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                   pass_fds=(3,), env={**os.environ, "HTTP_PROXY":"http://host-proxy:3128",
                   "HTTPS_PROXY":"http://host-proxy:3128", "http_proxy":"http://host-proxy:3128"})
first=p.stdout.readline()
info=json.loads(first.split("M2INFO ",1)[1]) if "M2INFO " in first else {}
res["info"]=info
# discover INNER node host pid
node_pid=None
for _ in range(50):
    for d2 in os.listdir("/proc"):
        if not d2.isdigit(): continue
        try: cl=open("/proc/%s/cmdline"%d2,"rb").read().split(b"\0")
        except OSError: continue
        if cl and cl[0]==b"/usr/bin/node" and any(MARK.encode() in c for c in cl):
            node_pid=int(d2); break
    if node_pid: break
    time.sleep(0.1)
res["node_pid"]=node_pid
trace=G2+"/out/st4/m2_node.trace"; terr=G2+"/out/st4/m2_strace.err"
st_rc=None; st_cmd=None
if node_pid:
    st_cmd=["strace","-f","-p",str(node_pid),"-e","trace=network","-tt","-T","-o",trace]
    st=subprocess.run(st_cmd, capture_output=True, text=True, timeout=90)
    st_rc=st.returncode
    open(terr,"w").write(st.stderr)
    try: p.wait(timeout=30)
    except subprocess.TimeoutExpired: p.kill()
out_rest=p.stdout.read(); err_rest=p.stderr.read()
res["trace"]={"command":" ".join(st_cmd) if st_cmd else None,"exit_code":st_rc,
  "stderr_hash":hashlib.sha256(open(terr,"rb").read()).hexdigest() if os.path.exists(terr) else None,
  "trace_hash":hashlib.sha256(open(trace,"rb").read()).hexdigest() if os.path.exists(trace) else None,
  "trace_exists":os.path.exists(trace)}
netpat=re.compile(r'\b(socket|connect|bind|listen|accept|sendto|recvfrom|setsockopt|getsockopt|socketpair|sendmsg|recvmsg)\(')
lines=[re.sub(r'^\d+\s+','',l.strip()) for l in open(trace,errors="replace")] if os.path.exists(trace) else []
netlines=[l for l in lines if netpat.search(l)]
res["trace"]["net_lines"]=[l[:150] for l in netlines[:30]]
res["trace"]["net_line_count"]=len(netlines)
res["trace"]["bwrap_only"]=bool(netlines) and all("AF_NETLINK" in l for l in netlines)
per={}
for l in netlines:
    nm=netpat.search(l).group(1)
    if "-1 EPERM" in l: r="EPERM"
    elif "= -1" in l: r=l.split("= -1 ")[-1].split(" ")[0]
    else: r="other"
    per.setdefault(nm,{}); per[nm][r]=per[nm].get(r,0)+1
res["network_syscalls"]=per
# assertions (fail-closed)
A=res["assertions"]
A["node_pid_discovered"]=node_pid is not None
A["strace_rc_zero"]=st_rc==0
A["trace_has_node_network_syscalls"]=len(netlines)>0
A["trace_not_bwrap_only"]=not res["trace"]["bwrap_only"]
A["socket_denied_direct"]=per.get("socket",{}).get("EPERM",0)>0
A["proxy_absent_in_probe"]=info.get("proxy")==[]
A["all_passed"]=all(A.values())
res["stderr_tail"]=err_rest[-200:]; res["stdout_tail"]=out_rest[-120:]
open(G2+"/out/m2_raw2.json","w").write(json.dumps(res,indent=2,sort_keys=True))
print("node_pid",node_pid,"strace_rc",st_rc,"net_lines",len(netlines))
print("syscalls:",json.dumps(per))
print("assertions:",json.dumps(A))
print("bwrap_only:",res["trace"]["bwrap_only"],"proxy:",info.get("proxy"))
print("ipv6:",repr(info.get("ipv6"))[:120]); print("dev:",repr(info.get("dev"))[:140]); print("route:",repr(info.get("route"))[:120])

