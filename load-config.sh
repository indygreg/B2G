#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

if [[ ! -n "$B2G_DIR" ]]; then
  B2G_DIR=$(cd `dirname $0`; pwd)
fi

. "$B2G_DIR/.config"
if [ $? -ne 0 ]; then
  echo Could not load .config. Did you run config.sh?
  exit -1
fi

if [ -f "$B2G_DIR/.userconfig" ]; then
  . "$B2G_DIR/.userconfig"
fi
