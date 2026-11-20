# Module build

The bundled x86-64 relocatable module was built with the prepared Valve
headers for `7.2.7-valve2-2-neptune-72-g31504582a073`, including Valve's
`Module.symvers` and objtool, using GCC 16.1.1 (20260625) and GNU binutils
2.46.1. The link and modpost completed. This build omits optional module
BTF because pahole 1.31 was unavailable, strips debug sections, and
is unsigned. The tester confirmed loading on the SteamOS configuration listed in the README.

The Valve header archive was retrieved from
[Valve’s SteamOS 3.9 repository](https://steamdeck-packages.steamos.cloud/archlinux-mirror/jupiter-3.9/os/x86_64/linux-neptune-72-headers-7.2.7.valve2-2-x86_64.pkg.tar.zst).
Its recorded SHA-256 is shown below. The ZIP contains the corresponding
module source, excluding Valve's separately obtained build headers and toolchain.

```bash
make -C "$KERNEL_BUILD" M="$PWD/kernel/source" CONFIG_DEBUG_INFO_BTF_MODULES= modules
objcopy --strip-debug kernel/source/hid-fanatec.ko kernel/hid-fanatec.ko
sha256sum kernel/hid-fanatec.ko > kernel/SHA256
```

`KERNEL_BUILD` points to the matching Valve package's prepared `build`
directory or the matching installed kernel's `/lib/modules/<release>/build`.
The update verifies its module hash and compares the module vermagic with
the previously installed driver before staging. A local rebuild may
produce different bytes.

Header package SHA-256

`57f3eea26d2ae0eb693d20a6759ab34dfcfd604d60f93f7c010804ba73f0859d`
