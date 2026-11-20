#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
exec python3 "$(dirname "$(readlink -f "$0")")/fullforce_update.py" "$@"
