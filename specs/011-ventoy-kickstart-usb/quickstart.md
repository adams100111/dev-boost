# Quickstart: validate ventoy-kickstart-usb (hermetic)
```sh
cd /home/dev/repos/dev-boost
bats tests/ventoy.bats   # make-usb safety + ventoy.json + ks.cfg layout + firstboot service
```
What green proves: make-usb refuses non-removable/system/partition/loop (SC-001); ks.cfg has var/lib/gdm
+ compress=zstd:1 + no swap (SC-002); firstboot runs install.sh --profile full then self-disables (SC-003);
ventoy.json valid + bound (SC-004); all hermetic, suite stays green (SC-005). Real build: `sudo ventoy/make-usb.sh /dev/sdX`.
