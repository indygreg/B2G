#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

B2G_HOME=$(cd `dirname $0`; pwd)

usage() {
    echo "Usage: $0 [marionette|mochitest] (frontend-args)"
    echo ""
    echo "'marionette' is the default frontend"
}

FRONTEND=$1
if [ -z "$FRONTEND" ]; then
  FRONTEND=marionette
else
  shift
fi

case "$FRONTEND" in
  mochitest)
    SCRIPT=$B2G_HOME/scripts/mochitest.sh ;;
  marionette)
    SCRIPT=$B2G_HOME/scripts/marionette.sh ;;
  --help|-h|help)
    usage
    exit 0;;
  *)
    usage
    echo "Error: Unknown test frontend: $FRONTEND" 1>&2
    exit 1
esac

echo $SCRIPT $@
$SCRIPT $@
