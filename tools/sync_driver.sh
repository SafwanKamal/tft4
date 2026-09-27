#!/bin/sh
# sync_driver.sh - copy the driver (driver/) into the CCS projects that use it.
#
# CCS builds the files it finds in a project folder, so each project keeps a
# copy of tft4.asm, font6x8.asm and tft4.h. driver/ is the one to edit; run
# this afterwards. tft4_config.inc is copied only where a project has none,
# because each project may use its own settings.
#
#   sh tools/sync_driver.sh              copy into demo/ and bench/TFT4_Bench/
#   sh tools/sync_driver.sh DIR...       ... and into these folders too
#                                        (for example ../tft4-invaders/tft4)
#   sh tools/sync_driver.sh --check      only report copies that differ (exit 1)
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHECK=0
[ "$1" = "--check" ] && { CHECK=1; shift; }
TARGETS="$ROOT/demo $ROOT/bench/TFT4_Bench $*"
FILES="tft4.asm font6x8.asm tft4.h"
status=0
for t in $TARGETS; do
  [ -d "$t" ] || { echo "no such folder: $t"; status=1; continue; }
  for f in $FILES; do
    if [ $CHECK = 1 ]; then
      cmp -s "$ROOT/driver/$f" "$t/$f" || { echo "differs: $t/$f"; status=1; }
    else
      cp "$ROOT/driver/$f" "$t/$f"
    fi
  done
  if [ ! -f "$t/tft4_config.inc" ]; then
    if [ $CHECK = 1 ]; then echo "missing: $t/tft4_config.inc"; status=1
    else cp "$ROOT/driver/tft4_config.inc" "$t/"; echo "added $t/tft4_config.inc"; fi
  fi
done
[ $CHECK = 1 ] && [ $status = 0 ] && echo "all copies match driver/"
exit $status
