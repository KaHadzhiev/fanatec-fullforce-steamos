# Upstream attribution and provenance

FullForce Wine compatibility implementation: **gotzl/fwfilterusb-wine**.

- Source: https://github.com/gotzl/fwfilterusb-wine
- Release: https://github.com/gotzl/fwfilterusb-wine/releases/tag/v0.0.2
- Exact commit: `ec2f9100ae104dcbc4eb6fd5cf9fcb2cb7c8304c`
- Official release archive: `fwfilterusb-v0.0.2.tar.gz`
- Archive SHA-256: `7de04776b736c38d3b4df1c4314ed20f6c2b55fe9766128e04140d19f5c1687c`
- License: GPL-2.0-or-later; upstream COPYING and source notices are included.

`vendor/fwfilterusb/` contains unmodified released binaries and installation resources. `vendor/fwfilterusb/source/` includes the corresponding source, build Makefile and upstream tests. Follow its README for build requirements. This package does not claim authorship of the upstream FullForce implementation. The added Python installer provides EVO detection, prerequisite checks, backup, installation orchestration and restoration.

The Linux module is based on **gotzl/hid-fanatecff** by Matthias Gorzellik
and contributors. The included source is derived from the upstream
[fwfilterusb branch commit e428f5a](https://github.com/gotzl/hid-fanatecff/commit/e428f5a156cf0048693fab453b16f9f06c2b886e),
which descends from the previously working `136cb2d65ae3db0f1ad75d4f6d6a688d8688699c`.
The 0.3 changes affect `hid-ftec.c`, `hid-ftec.h` and the added
`ftec-report-fifo.h`. The upstream LICENSE is included in `kernel/source/`.
The module is distributed under GPL-2.0, and upstream file notices are retained.
See BUILD.md for the binary build recipe.

Protontricks: https://github.com/Matoking/protontricks. It is a separately installed dependency, not bundled. Its own license applies.

`vendor-sha256.json` records the hashes of the bundled vendor files for corruption checks. These checks are not a digital signature or a guarantee of runtime behavior.
