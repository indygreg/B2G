#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

. setup.sh && time nice -n19 make $MAKE_FLAGS $@

ret=$?
echo -ne \\a
if [ $ret -ne 0 ]; then
  echo
  echo \> Build failed\! \<
  echo
  echo Build with \|./build.sh -j1\| for better messages
  echo If all else fails, use \|rm -rf objdir-gecko\| to clobber gecko and \|rm -rf out\| to clobber everything else.
else
  if echo $DEVICE | grep generic > /dev/null ; then
    echo Run \|./run-emulator.sh\| to start the emulator
    exit 0
  fi
  case "$1" in
  "gecko")
    echo Run \|./flash.sh gecko\| to update gecko
    ;;
  *)
    echo Run \|./flash.sh\| to flash all partitions of your device
    ;;
  esac
  exit 0
fi

exit $ret
