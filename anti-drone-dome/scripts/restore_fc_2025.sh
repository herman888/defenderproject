#!/bin/bash
# Restore Omnibus F4 to Betaflight 2025.12.4 (last known working USB).
exec "$(dirname "$0")/setup_omnibus_f4.sh" --flash
