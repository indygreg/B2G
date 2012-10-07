# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import unicode_literals

import os

from mach.base import BaseMixin
from mach.base import CommandArgument
from mach.base import CommandProvider
from mach.base import Command


@CommandProvider
class Emulator(BaseMixin):
    @Command('run-emulator', help='Run a B2G emulator.')
    def run_emulator(self):
        args = [os.path.join(self.cwd, 'run-emulator.sh')]

        return self._run_command(args, log_name=__name__,
            require_unix_environment=True, ignore_errors=True)


