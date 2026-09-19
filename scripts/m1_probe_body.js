
const fs=require("fs");
const R={};
function at(id, fn){ try { R[id]={ok:true, value:String(fn()).slice(0,300)}; }
  catch(e){ R[id]={ok:false, code:e.code||null, errno:(e.errno===undefined?null:e.errno), msg:String(e.message).slice(0,120)}; } }
function ex(p){ try { fs.accessSync(p); return "PRESENT"; } catch(e){ return e.code; } }
function rd(p){ try { return {ok:true, n:fs.readdirSync(p).length, entries:fs.readdirSync(p).slice(0,20).sort()}; }
  catch(e){ return {ok:false, code:e.code||null, errno:(e.errno===undefined?null:e.errno)}; } }
// P1 host filesystem visibility
R.p1={home:ex("/home/moiz/.raphael_m1_host_sentinel"), tmp:ex("/tmp/raphael_m1_host_sentinel"),
      etc_passwd:ex("/etc/passwd"), root_home:ex("/root"), repo_readme:ex("/home/moiz/raphael-2.0-rbsv2r/README.md")};
// P2 traversal
at("p2_provider_dotdot", ()=>fs.readFileSync("/provider/../../../etc/passwd","utf8"));
at("p2_node_dotdot", ()=>fs.readFileSync("/usr/bin/../../../etc/passwd","utf8"));
at("p2_fixture_dotdot_list", ()=>rd("/fixture/../.."));
at("p2_normalized", ()=>fs.statSync("/provider/./../fixture/../../etc"));
// P3 symlink escape
at("p3_proc_root_etc", ()=>fs.readFileSync("/proc/self/root/etc/passwd","utf8"));
at("p3_proc_exe", ()=>fs.readlinkSync("/proc/self/exe"));
at("p3_proc_root", ()=>fs.readlinkSync("/proc/self/root"));
at("p3_proc_cwd", ()=>fs.readlinkSync("/proc/self/cwd"));
// P4 provider/runtime writability
at("p4_provider_write", ()=>fs.writeFileSync("/provider/m1_probe_marker","x"));
at("p4_node_modules_write", ()=>fs.writeFileSync("/provider/node_modules/m1_probe_marker","x"));
at("p4_node_write", ()=>fs.writeFileSync("/usr/bin/node","x"));
at("p4_lib_write", ()=>fs.writeFileSync("/usr/lib/x86_64-linux-gnu/libc.so.6","x"));
at("p4_provider_unlink", ()=>fs.unlinkSync("/provider/package.json"));
at("p4_provider_mkdir", ()=>fs.mkdirSync("/provider/m1_dir"));
// P5 fixture
R.p5={fixture_exists:ex("/fixture/raphael_c1a_fixture.txt"), fixture_read_bytes:(()=>{try{return fs.statSync("/fixture/raphael_c1a_fixture.txt").size;}catch(e){return e.code;}})()};
at("p5_fixture_list", ()=>rd("/fixture"));
at("p5_fixture_write", ()=>fs.writeFileSync("/fixture/raphael_c1a_fixture.txt","x"));
at("p5_fixture_rename", ()=>fs.renameSync("/fixture/raphael_c1a_fixture.txt","/fixture/x"));
// P6 RAPHAEL source exposure
R.p6={substrate:ex("/home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/isolation_substrate.py"),
      git_head:ex("/home/moiz/raphael-2.0-rbsv2r/.git/HEAD"), tests:ex("/home/moiz/raphael-2.0-rbsv2r/tests")};
// P7 home/ssh/config
R.p7={home:ex("/home/moiz"), ssh:ex("/home/moiz/.ssh"), bashrc:ex("/home/moiz/.bashrc"),
      local:ex("/home/moiz/.local"), opencode_cfg:ex("/home/moiz/.config/opencode")};
// P8 sockets
R.p8={docker:ex("/var/run/docker.sock"), podman:ex("/run/podman/podman.sock"),
      containerd:ex("/run/containerd/containerd.sock"), systemd_private:ex("/run/systemd/private")};
// P9 devices
R.p9={dev_list:rd("/dev"), sys:ex("/sys"), proc:ex("/proc"),
      devs:{}};
for (const d of ["sda","nvme0n1","mem","kmem","kmsg","console","null","zero","urandom","tty","pts","shm","core","fuse"]) R.p9.devs[d]=ex("/dev/"+d);
// P10 privilege boundary
const st=fs.readFileSync("/proc/self/status","utf8");
function fld(n){const m=st.match(new RegExp("^"+n+":\\s*(.*)$","m"));return m?m[1].trim():null;}
R.p10={uid:process.getuid(), gid:process.getgid(), euid:process.geteuid(), egid:process.getegid(),
       CapEff:fld("CapEff"), CapPrm:fld("CapPrm"), CapBnd:fld("CapBnd"), NoNewPrivs:fld("NoNewPrivs"),
       Seccomp:fld("Seccomp"), Uid:fld("Uid"), Gid:fld("Gid"), Groups:fld("Groups")};
// P11 namespaces
const ns={}; for (const n of ["user","pid","net","ipc","uts","mnt","cgroup","time","pid_for_children","net"]) {
  try { ns[n]=fs.readlinkSync("/proc/self/ns/"+n); } catch(e){ ns[n]=e.code||null; } }
R.p11=ns;
// P12 process boundary (no readdir needed)
R.p12={proc1:ex("/proc/1"), proc2:ex("/proc/2"), proc_self:ex("/proc/self"), proc_host_high:ex("/proc/99999"),
       pid1_cmdline:(()=>{try{return fs.readFileSync("/proc/1/cmdline","utf8").replace(/\0/g," ").trim();}catch(e){return e.code;}})(),
       self_pid:process.pid, proc_list:rd("/proc")};
// P13 clone semantics (JS-reachable)
let forkres; try { require("child_process").execFileSync("/bin/true"); forkres="SPAWN_OK"; } catch(e){ forkres="DENIED/"+e.code+"/"+e.errno; }
R.p13={fork_like:forkres, thread_pool:"pending"};
// P14 credential changes
function tr(id,fn){ try { fn(); R[id]={ok:true,value:"CHANGED"}; } catch(e){ R[id]={ok:false,code:e.code||null,errno:(e.errno===undefined?null:e.errno)}; } }
tr("p14_setuid0",()=>process.setuid(0));
tr("p14_setgid0",()=>process.setgid(0));
if (process.setgroups) tr("p14_setgroups",()=>process.setgroups([0]));
// P15 cgroup boundary
at("p15_read_sys_fs_cgroup", ()=>rd("/sys/fs/cgroup"));
at("p15_write_cgroup_procs", ()=>fs.writeFileSync("/sys/fs/cgroup/cgroup.procs","1"));
R.p15_sys_exists=ex("/sys");
// P16 double-fork preparation
let dbl; try { require("child_process").spawn("/bin/true"); dbl="SPAWN_OK"; } catch(e){ dbl="DENIED/"+e.code+"/"+e.errno; }
R.p16={spawn:dbl, setsid_available:(typeof process.setsid)};
// async fs => libuv threadpool => clone(thread)
fs.readFile("/usr/share/nodejs/cjs-module-lexer/lexer.js","utf8",(e,d)=>{ R.p13.thread_pool = e ? ("ERR/"+e.code) : ("OK/"+String(d).length);
  process.stdout.write("M1JSON "+JSON.stringify(R)); });