#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$scratch/linux"
printf '#include <string.h>\n' > "$scratch/linux/string.h"
# Compile the shipped worker, submit and stop routines against a small
# deterministic workqueue/USB stand-in to exercise the actual queue policy.
sed -n '/^static void ftec_ff_work(/,/^static int ftec_client_ll_raw_request(/{ /^static int ftec_client_ll_raw_request(/d; p; }' \
    kernel/source/hid-ftec.c > "$scratch/report-worker.inc"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$scratch" -Ikernel/source \
    tests/report_queue.c -o "$scratch/report_queue"
"$scratch/report_queue"
