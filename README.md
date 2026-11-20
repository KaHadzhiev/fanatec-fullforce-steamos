# Fanatec FullForce on SteamOS for Assetto Corsa EVO

For Assetto Corsa EVO (Steam app 3058630), a Fanatec GT DD Pro in PC mode
(USB `0eb7:0020`), and SteamOS 3.9.5 with kernel
`7.2.7-valve2-2-neptune-72-g31504582a073`. Version 0.3 was tested on the setup below. The package is free and open source.

## Hardware test reported on 20 November 2026

| Item | Tested setup |
| --- | --- |
| Wheelbase | Fanatec Gran Turismo DD Pro (GT DD Pro) |
| Connection | USB in PC mode, `0eb7:0020` |
| Detected base family and rim | Family `17`, rim ID `16` |
| OS | SteamOS 3.9.5, x86-64 |
| Kernel | `7.2.7-valve2-2-neptune-72-g31504582a073` |
| Game | Assetto Corsa EVO, Steam app `3058630`, running through Proton |
| Linux driver | `hid_fanatec`, loaded version `fullforce-0.3-test` |
| Wine component | gotzl/fwfilterusb-wine v0.0.2 |

The tester confirmed that the module loaded after reboot and reported a
normal baseline drive with the EVO add-on still undone. After installing
the add-on, the tester reported that FullForce worked perfectly. This is
a qualitative result from one configuration. Exact FPS, frame times,
car, track, firmware, SteamOS host model and Proton version were not
recorded. Post-install reboot persistence, disconnect/reconnect under load,
other wheels, kernels and games have no recorded hardware result here.

## What changed

0.2 registered gotzl's Wine compatibility driver v0.0.2. The wheel produced
FullForce, but EVO lost FPS and simulation speed. Undo restored normal
performance on the same car and track. The Wine driver answers the SDK's
device/configuration queries. The Linux virtual HID driver's synchronous
USB output path is a plausible source of stalls. A game-side trace or
hardware trace is needed to establish the precise cause.

Upstream's `fwfilterusb` branch defers report 255 to a workqueue. Its single
pending slot can overwrite any pending report, including LED changes or
stream/control data. The bundled Wine source does not identify which
payloads can be discarded safely. The branch also destroys its workqueue
before disconnecting the virtual HID client, leaving a race with writers.

0.3 preserves FIFO order for accepted report-255 output writes to the
target device. Four packets can be queued plus one in flight. Acceptance
returns immediately. When full, the driver rejects the new packet with
`EBUSY`, which Wine or EVO may treat as a failed write. Successful acceptance
does not guarantee delivery. USB failures are logged with rate limiting.
USB transport remains synchronous in the worker. Reports outside this path,
including ordinary PID force-feedback commands, still use the upstream
dispatch. Their ordering relative to deferred reports can differ.

On removal and the relevant probe failures, the driver closes submissions
under the same lock used to schedule work, drops queued packets and waits
for the in-flight call before releasing the virtual HID client and the USB
transport. The driver logs accepted report, overrun and USB error totals on teardown.
The branch’s optional shift-light recoloring defaults to off in this build.
A pre-existing USB timeout can still delay teardown.

## Install and test

1. Download the [0.3 installation ZIP](https://github.com/KaHadzhiev/fanatec-fullforce-steamos/archive/bb626b701ceb58ec81fa6d3a3bd48f829f1b70e7.zip), or clone this repository. In Desktop Mode, extract the ZIP and open Konsole in the folder containing `kernel_update.py`. Close EVO and other Proton games.
   Keep 0.2 undone. Check `uname -r` against the version above. The working
   `hid_fanatec` must already be installed as a disk module for that kernel.
2. Run this to back up the currently selected module and stage 0.3.

   ```bash
   sudo python3 kernel_update.py install
   ```

   If the module filesystem is read-only, run
   `sudo steamos-readonly disable`, retry the kernel command, and return the
   filesystem to read-only with `sudo steamos-readonly enable`. The script
   uses the existing module location and checks its build flags. If
   installation fails after replacement, it attempts to restore the
   original. Reboot, then connect or power on the wheel in PC mode.
3. Confirm that this prints `fullforce-0.3-test`.

   ```bash
   cat /sys/module/hid_fanatec/version
   ```

   Launch EVO once with the add-on undone and confirm steering, pedals,
   ordinary FFB and baseline performance. Exit EVO. Enable the add-on as
   your Steam user.

   ```bash
   bash update.sh --check
   bash update.sh
   ```

   If Protontricks is missing, the install command can install it from an
   existing user Flathub remote. If no remote exists, install Protontricks
   through Discover. If detection finds multiple prefixes, add
   `--prefix /path/to/steamapps/compatdata/3058630/pfx`.
4. Compare EVO with **FullForce OFF**, then **ON** at modest strength. Use
   the same Proton version, car, track, weather, graphics and ordinary
   FFB settings. Compare FPS, frametime spikes and simulation speed,
   and check that ON produces recognizable FullForce. Exit and relaunch
   EVO, then repeat after reboot. With EVO closed, disconnect/reconnect
   the wheel and check the kernel log and ordinary FFB. Record any
   `report-255 OUT` messages along with the wheel firmware/Proton version.
   If the slowdown returns, roll back before continuing to play.

## Rollback

Close EVO and other Wine applications. Restore the EVO prefix first, and
then restore the original kernel module and reboot.

```bash
bash update.sh --undo
sudo python3 kernel_update.py undo
```

Use the same read-only filesystem procedure if needed. The kernel backup is
under `/var/lib/fanatec-fullforce/<kernel-release>/`. The kernel script
verifies the saved original and refuses to overwrite an unrelated module
change. The installer does not hot-swap modules. Verify normal FFB after
reboot. Prefix rollback restores the entire saved EVO prefix. It retains
the current one as `pfx-before-undo-<timestamp>` beside `pfx`, including
newer prefix-local settings and saves. Check both that directory and Steam
Cloud reconciliation before discarding anything. The installer preserves
symlinks, so files outside the prefix reached through links aren’t restored
from the snapshot.

## Troubleshooting

- **Python cannot open `kernel_update.py`.** Open the extracted folder that
  contains the file in Dolphin and press **F4** to open a terminal there.
- **Read-only file system.** Use the temporary SteamOS read-only procedure
  in step 2. Re-enable protection even if the install command fails.
- **FullForce missing or slowdown returns.** Close EVO. Check the loaded
  version from step 3 and use the rollback steps if needed. For an issue
  report, include wheel and rim models, firmware, SteamOS and Proton
  versions, `uname -r`, FPS and simulation speed with FullForce OFF and ON,
  and relevant `report-255 OUT` messages. Share only the relevant log lines.
  Do not upload the Proton prefix or its registry.

## Source and tests

`kernel/source/` contains corresponding kernel module source. With
matching, prepared kernel headers, build with
`make -C /lib/modules/$(uname -r)/build M="$PWD/kernel/source"`.
See BUILD.md for the shipped build details and THIRD_PARTY.md for source
versions, credits and license information.

```bash
python3 -m unittest discover -s tests -v
bash tests/test_report_queue.sh
```

The tests cover simulated Proton-prefix install and rollback, filesystem
module replacement and recovery, and the report queue's ordering, payload
copy, saturation, USB error count and shutdown gating. The queue test
uses a simulated workqueue and USB transport. The hardware result above covers one reported configuration. See [BUILD.md](BUILD.md) for build details and [THIRD_PARTY.md](THIRD_PARTY.md) for licenses and credits.
