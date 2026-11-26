#!/bin/sh
# THE LAUNCHER (harness/launcher.py). No arguments = the menu.
cd "$(dirname "$0")" && exec python3 -m harness.launcher "$@"
