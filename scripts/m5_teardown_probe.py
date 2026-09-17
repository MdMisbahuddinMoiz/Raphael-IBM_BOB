import json, os, re, subprocess, time, hashlib
G2="/tmp/raphael_g2"; OUT=G2+"/out"; os.makedirs(OUT, exist_ok=True)
uid=os.getuid()
SCOPE=f"/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service/app.slice"
unit=f"raphael-m5-{int(time.time())}"
scope_cg=f"{SCOPE}/{unit}.scope"
C=f"{scope_cg}/raphael-child"
inner=(f"C={C}; mkdir -p $C; "
       f"(echo $BASHPID > $C/cgroup.procs; exec sleep 300) & exec sleep 300")
res={"unit":unit,"scope_cgroup":scope_cg,"child_cgroup":C,"steps":{}}
env={**os.environ,"XDG_RUNTIME_DIR":"/run/user/1000","DBUS_SESSION_BUS_ADDRESS":"unix:path=/run/user/1000/bus"}
p=subprocess.Popen(["systemd-run","--user","--scope","--unit",unit,"-p","Delegate=yes",
                    "--","bash","-c",inner], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   text=True, env=env)
def rd(path):
    try: return open(path).read().strip()
    except OSError as e: return "ERR:"+e.strerror
t0=time.time()
target=None
for _ in range(60):
    if os.path.isdir(C):
        procs=rd(C+"/cgroup.procs")
        if procs and not procs.startswith("ERR"):
            target=int(procs.split()[0]); break
    time.sleep(0.1)
res["steps"]["delegate_parent_subtree_control"]=rd(scope_cg+"/cgroup.subtree_control")
res["steps"]["child_exists"]=os.path.isdir(C)
res["target_pid"]=target
if target:
    stat=open(f"/proc/{target}/stat").read()
    rp=stat.rfind(")"); fields=stat[rp+1:].split()
    starttime=fields[19]
    res["steps"]["starttime_before"]=starttime
    res["steps"]["state_before"]=fields[0]
    res["steps"]["cmdline_before"]=open(f"/proc/{target}/cmdline","rb").read().replace(b"\0",b" ").decode().strip()
    res["steps"]["events_before"]=rd(C+"/cgroup.events")
    res["steps"]["procs_before"]=rd(C+"/cgroup.procs")
    res["steps"]["memory_max"]=rd(C+"/memory.max"); res["steps"]["pids_max"]=rd(C+"/pids.max")
    tkill=time.time()
    open(C+"/cgroup.kill","w").write("1")
    res["steps"]["kill_written"]=True
    populated=None
    for i in range(60):
        ev=rd(C+"/cgroup.events")
        if "ERR" in ev: res["steps"]["events_error"]=ev; break
        m=re.search(r'populated (\d+)', ev)
        if m and m.group(1)=="0":
            populated="0"; res["steps"]["populated_zero_after_polls"]=i+1; break
        time.sleep(0.05)
    res["steps"]["kill_to_populated_zero_s"]=round(time.time()-tkill,3)
    res["steps"]["events_after"]=rd(C+"/cgroup.events")
    time.sleep(0.2)
    # PID/starttime anti-reuse
    if os.path.exists(f"/proc/{target}"):
        st2=open(f"/proc/{target}/stat").read(); rp2=st2.rfind(")"); f2=st2[rp2+1:].split()
        res["steps"]["pid_after"]="PRESENT"; res["steps"]["state_after"]=f2[0]
        res["steps"]["starttime_after"]=f2[19]
        res["steps"]["same_process"]=(f2[19]==starttime)
    else:
        res["steps"]["pid_after"]="ABSENT"; res["steps"]["state_after"]=None
        res["steps"]["starttime_after"]=None; res["steps"]["same_process"]=False
    res["steps"]["target_terminated"]=(res["steps"]["pid_after"]=="ABSENT"
        or res["steps"]["state_after"]=="Z")
    res["steps"]["starttime_reuse_guard"]="PID present? starttime compared; Z=>terminated"
    # leftover process observation: distinguish TARGET (must be gone) from HOLDER (expected)
    leftover=[]; target_live=False
    for d in os.listdir("/proc"):
        if not d.isdigit(): continue
        try:
            cl=open(f"/proc/{d}/cmdline","rb").read().replace(b"\0",b" ").decode()
            st=open(f"/proc/{d}/stat").read(); st=st[st.rfind(")")+1:].split()[0]
        except OSError: continue
        if "sleep 300" in cl:
            leftover.append({"pid":int(d),"state":st})
            if int(d)==target and st!="Z": target_live=True
    res["steps"]["leftover_sleep300"]=leftover
    res["steps"]["target_live_after_kill"]=target_live
    res["steps"]["leftover_observation"]=("CONFIRMED_ABSENT" if target_live is False and
        not any(x["state"]!="Z" for x in leftover if x["pid"]==target) else "CONFIRMED_PRESENT")
    res["steps"]["holder_expected_alive"]=[x for x in leftover if x["pid"]!=target]
    res["steps"]["child_rmdir"]=subprocess.run(["rmdir",C],capture_output=True,text=True).returncode==0
res["scope_stop"]=subprocess.run(["systemctl","--user","stop",unit+".scope"],capture_output=True,text=True,env=env).returncode
time.sleep(0.5)
try: p.kill()
except Exception: pass
res["scope_gone"]=not os.path.exists(scope_cg)
open(G2+"/out/m5_raw.json","w").write(json.dumps(res,indent=2,sort_keys=True))
print("target",target,"| subtree",res["steps"].get("delegate_parent_subtree_control"))
print("events_before",res["steps"].get("events_before"),"events_after",res["steps"].get("events_after"))
print("populated_zero_after_polls",res["steps"].get("populated_zero_after_polls"),"in",res["steps"].get("kill_to_populated_zero_s"),"s")
print("pid_after",res["steps"].get("pid_after"),"same_process",res["steps"].get("same_process"))
print("leftover",res["steps"].get("leftover_observation"),res["steps"].get("leftover_sleep300"))
print("child_rmdir",res["steps"].get("child_rmdir"),"scope_gone",res["scope_gone"])
