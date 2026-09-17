import json, os, re, subprocess, sys, hashlib, time
sys.path.insert(0, "/home/moiz/raphael-2.0-rbsv2r")
from raphael_ibm_bob.isolation_substrate import (SandboxSpec, ProviderRef, FixtureRef,
                                                 build_bwrap_argv, NODE_RUNTIME, SCRATCH_MODE,
                                                 node_runtime_closure)
from raphael_ibm_bob.seccomp_policy import build_policy
REPO="/home/moiz/raphael-2.0-rbsv2r"; G2="/tmp/raphael_g2"
OUT=REPO+"/docs/integration/phase-2c-m2"; os.makedirs(OUT, exist_ok=True)
JS=r'''
const fs=require("fs"); const R={};
function rd(p){try{return fs.readFileSync(p,"utf8").slice(0,500)}catch(e){return "ERR:"+e.code}}
R.p1_dev=rd("/proc/net/dev"); R.p1_if_inet6=rd("/proc/net/if_inet6"); R.p1_fib=rd("/proc/net/fib_trie");
R.p2_route=rd("/proc/net/route"); R.p2_ipv6_route=rd("/proc/net/ipv6_route");
R.p3_resolv=(()=>{try{fs.accessSync("/etc/resolv.conf");return "PRESENT"}catch(e){return e.code}})();
R.p3_hosts=(()=>{try{fs.accessSync("/etc/hosts");return "PRESENT"}catch(e){return e.code}})();
R.p11_proxy=Object.keys(process.env).filter(k=>/proxy/i.test(k)).sort();
R.p10_netns=fs.readlinkSync("/proc/self/ns/net");
function attempt(fn, ms){ return new Promise(res=>{ let done=false; const fin=o=>{if(!done){done=true;res(o)}};
  try{ fn(fin); }catch(e){ fin({ok:false,code:e.code||null,errno:(e.errno===undefined?null:e.errno)}); }
  setTimeout(()=>fin({ok:false,timeout:true,code:"TIMEOUT"}), ms); }); }
(async()=>{
  R.p4_inet = await attempt(cb=>{ const s=require("net").connect({host:"127.0.0.1",port:1});
    s.on("error",e=>cb({ok:false,code:e.code,errno:e.errno})); s.on("connect",()=>cb({ok:true,value:"CONNECTED"})); },1200);
  R.p5_inet6 = await attempt(cb=>{ const s=require("net").connect({host:"::1",port:1});
    s.on("error",e=>cb({ok:false,code:e.code,errno:e.errno})); s.on("connect",()=>cb({ok:true,value:"CONNECTED"})); },1200);
  R.p6_tcp = await attempt(cb=>{ const s=require("net").connect({host:"192.0.2.1",port:80});
    s.on("error",e=>cb({ok:false,code:e.code,errno:e.errno})); s.on("connect",()=>cb({ok:true,value:"CONNECTED"})); },1200);
  R.p7_udp = await attempt(cb=>{ const d=require("dgram").createSocket("udp4");
    d.on("error",e=>cb({ok:false,code:e.code,errno:(e.errno===undefined?null:e.errno)}));
    d.send(Buffer.from("x"),1,"127.0.0.1",e=>{ if(e) cb({ok:false,code:e.code,errno:e.errno}); }); },1200);
  R.p8_listen = await attempt(cb=>{ const srv=require("net").createServer();
    srv.on("error",e=>cb({ok:false,code:e.code,errno:e.errno})); srv.listen(0,"127.0.0.1",()=>cb({ok:true,value:"LISTENING"})); },1200);
  R.p3_dns = await attempt(cb=>{ require("dns").resolve4("raphael-probe.invalid",(e,a)=>cb(e?{ok:false,code:e.code,errno:(e.errno===undefined?null:e.errno)}:{ok:true,value:String(a)})); },1800);
  process.stdout.write("M2JSON "+JSON.stringify(R));
})();
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
 "uid_gid":[base[base.index("--uid")+1],base[base.index("--gid")+1]],
 "unshare_net":("--unshare-net" in base),"seccomp_fd":base[base.index("--seccomp")+1],
 "cap_drop":base[base.index("--cap-drop")+1]}
host_net=os.readlink("/proc/self/ns/net")
fd=os.open(G2+"/policy.bpf",os.O_RDONLY); os.dup2(fd,3)
t0=time.time(); r=subprocess.run(argv,capture_output=True,text=True,pass_fds=(3,),timeout=120)
P=json.loads(r.stdout.split("M2JSON ",1)[1]) if "M2JSON " in r.stdout else {}
# host-side syscall-level trace of the same probe
os.makedirs(G2+"/out/st3",exist_ok=True)
subprocess.run(["strace","-f","-ff","-qq","-o",G2+"/out/st3/tr"]+base[:-2]+[NODE_RUNTIME,"-e",JS],
               capture_output=True,text=True,pass_fds=(3,),timeout=120)
net_pat=re.compile(r'\b(socket|connect|bind|listen|accept|sendto|recvfrom|setsockopt|getsockopt|socketpair)\(.*')
node_file=None
for fn in sorted(os.listdir(G2+"/out/st3")):
    if fn.startswith("tr."):
        txt=open(G2+"/out/st3/"+fn,errors="replace").read()
        if 'execve("/usr/bin/node"' in txt: node_file=fn; break
hits=[]
for fn in ([node_file] if node_file else []):
    for line in open(G2+"/out/st3/"+fn,errors="replace"):
        m=net_pat.search(line)
        if m: hits.append(re.sub(r'^\d+\s+','',line.strip())[:160])
summary={}
for h in hits:
    nm=h.split("(")[0]
    res="-1 EPERM" if "-1 EPERM" in h else ("SUCCESS" if "= -1" not in h else h.split("= ")[-1][:20])
    summary.setdefault(nm,{}).setdefault(res,0); summary[nm][res]+=1
r2={"freeze":freeze,"host_net_ns":host_net,"rc":r.returncode,"stderr":r.stderr.strip()[:200],
    "probe":P,"net_syscall_trace":summary,"net_trace_lines":hits[:40],
    "trace_files":len([f for f in os.listdir(G2+"/out/st3") if f.startswith("tr.")]),
    "elapsed_s":round(time.time()-t0,2)}
open(G2+"/out/m2_raw.json","w").write(json.dumps(r2,indent=2,sort_keys=True))
print("rc",r.returncode,"| net syscalls:",json.dumps(summary))
print("p1_dev:",repr(P.get("p1_dev"))[:160]); print("p2_route:",repr(P.get("p2_route"))[:160])
print("p3_resolv:",P.get("p3_resolv"),"dns:",P.get("p3_dns"),"netns:",P.get("p10_netns"),"host_net:",host_net)
print("p4:",P.get("p4_inet"),"p5:",P.get("p5_inet6"),"p6:",P.get("p6_tcp"),"p7:",P.get("p7_udp"),"p8:",P.get("p8_listen"))
print("proxy:",P.get("p11_proxy"))
