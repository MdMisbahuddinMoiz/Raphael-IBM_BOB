# SENTINEL REPORT — Target Deployment: Stapler (10.66.0.159) on icabr0 Lab

**To:** SENTINEL  
**From:** RAPHAEL-FORGE v4 (Evaluation-Surgeon / Reality-Anchored)  
**Date:** 2026-08-02  
**Status:** ✅ TARGET STARTED — LAB DEFECT FOUND & FIXED — RECON CAPTURED

---

## EXECUTIVE SUMMARY

Deployed the **Stapler** VulnHub VM (`target/Stapler/` — g0tmi1k, BsidesLondon 2016) onto the isolated `icabr0` lab bridge (10.66.0.0/24). During boot validation, discovered a **latent lab defect**: both QEMU VMs (LupinOne + Stapler) were using the **identical MAC `52:54:00:12:34:56`** (QEMU default when `mac=` is unspecified). Two hosts with the same MAC on one bridge causes ARP flapping and unreliable connections — a first-failing-boundary defect (Rule 24) that would have corrupted every subsequent engagement. Applied the minimal repair (unique MAC `52:54:00:12:34:57` on the Stapler VM, script-level only — zero `src/` changes) and redeployed.

**Headline finding:** Stapler is live at **10.66.0.159** with 4 open services (FTP/SSH/HTTP/MySQL) and **anonymous FTP login confirmed**. Full recon captured. Both VMs now coexist on the bridge with unique MACs.

---

## INFRASTRUCTURE STATE

| Resource | Status | Details |
|----------|--------|---------|
| Bridge `icabr0` | ✅ UP | 10.66.0.254/24, `ip link show icabr0` — state UP |
| DHCP (dnsmasq) | ✅ Running | PID 5540, range 10.66.0.100–200, `--port=0 --no-resolv` |
| LupinOne VM | ✅ Running | PID 5582, 10.66.0.158, MAC `52:54:00:12:34:56` (unchanged) |
| **Stapler VM (NEW)** | ✅ Running | PID 281254, **10.66.0.159**, MAC `52:54:00:12:34:57` (fixed) |
| VNC consoles | ✅ | LupinOne :5902, Stapler :5903 (127.0.0.1 only) |
| Docker | ✅ 15 containers Up | incl. `dvwa`, `kali-tools` (has openssh-client + sshpass) |

---

## TARGET START PROCEDURE (as executed)

1. **Identified target artifact** — `target/Stapler/Stapler-disk1.vmdk` (OVF: 20 GiB virtual, 1 vCPU, 1024 MB, PCNet32 NIC).
2. **Converted disk** — `qemu-img convert -f vmdk -O qcow2` → `test-target/stapler.qcow2` (2.06 GiB on disk, 20 GiB virtual, zlib compression, no corruption).
3. **Created deploy script** — `current-state/reports/_deploy_stapler.sh` (mirrors `_deploy_lupin.sh`: tap2 → icabr0, KVM accel, VNC :3, daemonized).
4. **Started VM** — `qemu-system-x86_64 -accel kvm -m 1024 -smp 1 -drive stapler.qcow2 -device pcnet -vnc :3`.
5. **Verified boot** — DHCP lease acquired: **10.66.0.159 / hostname `red`** (dnsmasq log DHCPACK 07:34:51).
6. **Full port scan** — 4 services open (see below).

---

## ⚠️ LAB DEFECT FOUND & FIXED (Rule 24 — first failing boundary)

**Symptom:** After first Stapler boot, `ip neigh` showed **both** 10.66.0.157 (Stapler) and 10.66.0.158 (LupinOne) resolving to the **same MAC `52:54:00:12:34:56`**.

**Root cause:** QEMU's default MAC (`52:54:00:12:34:56`) is assigned when `-device` is given without `mac=`. Neither `_deploy_lupin.sh` (e1000) nor the original `_deploy_stapler.sh` (pcnet) specified a MAC.

**Impact if unfixed:** ARP cache flapping, dropped/duplicated frames, broken TCP sessions — would corrupt scan results and make the Stapler engagement untrustworthy.

**Minimal repair (script-level, Rule 44):** Added `mac=52:54:00:12:34:57` to Stapler's `-device pcnet` line. Killed and redeployed. Verifiable fix:
- Lease table: `10.66.0.159 52:54:00:12:34:57 red`
- `ip neigh`: `10.66.0.158 → 52:54:00:12:34:56` (LupinOne, REACHABLE), `10.66.0.159 → 52:54:00:12:34:57` (Stapler, REACHABLE)

---

## RECON — STAPLER (10.66.0.159)

### Open Ports & Services (nmap -sS -sV -sC)

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | FTP | vsftpd 2.0.8 or later |
| 22/tcp | SSH | OpenSSH 7.2p2 Ubuntu-4 |
| 80/tcp | HTTP | PHP CLI server 5.5+ |
| 3306/tcp | MySQL | MySQL 5.7.12-0ubuntu1 |

OS: Linux, Ubuntu-family (OpenSSH `Ubuntu-4`, MySQL `5.7.12-0ubuntu1`).

### Banner Checks
- **FTP (anonymous):** `USER anonymous` → `331 Please specify the password` → `230 Login successful` ✅ (anonymous access confirmed — primary entry vector)
- **HTTP:** Root `/` returns `404 Not Found` (PHP built-in server; content-length 533)
- **SSH:** `SSH-2.0-OpenSSH_7.2p2 Ubuntu-4`

### Known challenge notes (from readme)
- Average beginner/intermediate; **2+ paths to limited shell, 3+ paths to root**
- Made for BsidesLondon 2016 by g0tmi1k

---

## DATA / ARTIFACTS

| Artifact | Location | Purpose |
|----------|----------|---------|
| Stapler VM disk | `target/Stapler/Stapler-disk1.vmdk` | Original artifact (untouched) |
| Converted disk | `test-target/stapler.qcow2` | QEMU boot image (2.06 GiB) |
| Deploy script | `current-state/reports/_deploy_stapler.sh` | Boot Stapler (now with fixed MAC) |
| Boot check | `scripts/wait_stapler_boot.sh` | Waits for DHCP lease |
| Recon | `scripts/stapler_recon.sh`, `stapler_fullscan.sh`, `stapler_nmap.sh`, `stapler_banner.sh` | Port + banner capture |
| VNC capture | `scripts/stapler_vnc3.sh` | Console capture (needs pip bootstrap — see below) |

---

## NOTES / OPEN ITEMS

1. **vncdotool not installed** — host venv has no `pip` module (`No module named pip`); system python is 3.14.4 (must not use). VNC console capture deferred; not blocking (services verified via direct TCP).
2. **LupinOne MAC** — left unchanged (`52:54:00:12:34:56`) to preserve prior telemetry references (evidence points to 10.66.0.158). The collision is now resolved by differentiating Stapler.
3. **Tap cleanup** — `tap2` tuntap persists across qemu restarts (`Device or resource busy` on re-add is benign; qemu still attaches). Not a defect.
4. **Hostname `red`** — Stapler identifies as `red` in DHCP (expected — this box uses a non-default hostname).
5. **Next step (pending SENTINEL direction):** broker-gated engagement against Stapler — FTP anonymous dump → web enum (PHP built-in server) → MySQL → SSH. Requires adding Stapler as target in `ica_live_engagement.py` (script-level) with its own RoE block.

---

## GOVERNANCE

- **Strike count: 0/3** — zero `src/` changes. All modifications: deploy script (mac=), new recon scripts, qemu-img conversion (test artifact).
- **Rule 44 applied:** minimal repair to script, not architecture.
- **Rule 24 applied:** first failing boundary was the MAC collision — traced, fixed, verified.
- **Scope discipline:** target is a local VulnHub lab VM on isolated bridge; no DIB-VDP scope applies (read-only context, per operator instruction).
- **DIB-VDP alignment (standing guidance):** minimal-impact proof-only, no DoS, no exfiltration, no public disclosure — consistent with broker-gated engagement model.

---

## VERIFICATION CHAIN (mental simulation → confirmed)

1. Convert: `qemu-img info` → qcow2 valid, 20 GiB, not corrupt ✅
2. Boot: qemu PID 281254, VNC :3 listening, tap2 up/master icabr0 ✅
3. DHCP: dnsmasq lease `52:54:00:12:34:57 → 10.66.0.159 red` ✅
4. Reachability: direct TCP probes → 21/22/80/3306 OPEN ✅
5. MAC uniqueness: `ip neigh` → two distinct MACs, both REACHABLE ✅

---

*Prepared by RAPHAEL-FORGE v4. All raw data reproducible via scripts referenced above.*
