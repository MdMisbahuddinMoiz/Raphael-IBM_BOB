#!/bin/bash
# Deploy Stapler VM on icabr0 (10.66.0.0/24) — VulnHub CTF box by g0tmi1k
set -x
echo 'mi11xpro' | sudo -S -p '' ip tuntap add tap2 mode tap 2>&1
echo 'mi11xpro' | sudo -S -p '' ip link set tap2 master icabr0 2>&1
echo 'mi11xpro' | sudo -S -p '' ip link set tap2 up 2>&1

sudo qemu-system-x86_64 \
  -accel kvm \
  -m 1024 -smp 1 \
  -drive file=/home/yaser/raphael-2.0/test-target/stapler.qcow2,format=qcow2,if=ide \
  -netdev tap,id=net1,ifname=tap2,script=no,downscript=no \
  -device pcnet,netdev=net1,mac=52:54:00:12:34:57,addr=03.0 \
  -vnc 127.0.0.1:3 \
  -daemonize
echo "QEMU_EXIT=$?"
sleep 2
ps aux | grep 'stapler' | grep -v grep | head -2
ip link show tap2 | grep -E 'state|master'