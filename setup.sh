#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

. load-config.sh

VARIANT=${VARIANT:-eng}
LUNCH=${LUNCH:-full_${DEVICE}-${VARIANT}}

export USE_CCACHE=yes
export GECKO_PATH
export GAIA_PATH
export GAIA_DOMAIN
export GAIA_PORT
export GAIA_DEBUG
export GECKO_OBJDIR
. build/envsetup.sh && lunch $LUNCH
