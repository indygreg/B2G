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
class Flash(BaseMixin):
    @Command('flash', help='Flash a device with a B2G image.')
    @CommandArgument('--serial-number', '-s',
        help='Serial number to pass to ADB.')
    @CommandArgument('project', choices=('gecko', 'gaia', 'time'),
        help='What to flash on the device.')
    def flash(self, project, serial_number=None):
        args = [os.path.join(self.cwd, 'flash.sh')]

        if serial_number is not None:
            args.append(serial_number)

        args.append(project)

        return self._run_command(args, log_name=__name__,
            require_unix_environment=True, ignore_errors=True)



