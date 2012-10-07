# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import unicode_literals

import logging
import os
import subprocess
import sys
import types

from mozprocess.processhandler import ProcessHandlerMixin

from mach.registrar import register_method_handler


# Perform detection of operating system environment. This is used by command
# execution. We only do this once to save redundancy. Yes, this can fail module
# loading. That is arguably OK.
if 'SHELL' in os.environ:
    _current_shell = os.environ['SHELL']
elif 'MOZILLABUILD' in os.environ:
    _current_shell = os.environ['MOZILLABUILD'] + '/msys/bin/sh.exe'
elif 'COMSPEC' in os.environ:
    _current_shell = os.environ['COMSPEC']
else:
    raise Exception('Could not detect environment shell!')

_in_msys = False

if os.environ.get('MSYSTEM', None) == 'MINGW32':
    _in_msys = True

    if not _current_shell.lower().endswith('.exe'):
        _current_shell += '.exe'


def CommandProvider(cls):
    """Class decorator to denote that it provides subcommands for Mach.

    When this decorator is present, mach looks for commands being defined by
    methods inside the class.
    """

    # The implementation of this decorator relies on the parse-time behavior of
    # decorators. When the module is imported, the method decorators (like
    # @Command and @CommandArgument) are called *before* this class decorator.
    # The side-effect of the method decorators is to store specifically-named
    # attributes on the function types. We just scan over all functions in the
    # class looking for the side-effects of the method decorators.

    # We scan __dict__ because we only care about the classes own attributes,
    # not inherited ones. If we did inherited attributes, we could potentially
    # define commands multiple times. We also sort keys so commands defined in
    # the same class are grouped in a sane order.
    for attr in sorted(cls.__dict__.keys()):
        value = cls.__dict__[attr]

        if not isinstance(value, types.FunctionType):
            continue

        parser_args = getattr(value, '_mach_command', None)
        if parser_args is None:
            continue

        arguments = getattr(value, '_mach_command_args', None)

        register_method_handler(cls, attr, (parser_args[0], parser_args[1]),
            arguments or [])

    return cls


class Command(object):
    """Decorator for functions or methods that provide a mach subcommand.

    The decorator accepts arguments that would be passed to add_parser() of an
    ArgumentParser instance created via add_subparsers(). Essentially, it
    accepts the arguments one would pass to add_argument().

    For example:

        @Command('foo', help='Run the foo action')
        def foo(self):
            pass
    """
    def __init__(self, *args, **kwargs):
        self._command_args = (args, kwargs)

    def __call__(self, func):
        func._mach_command = self._command_args

        return func


class CommandArgument(object):
    """Decorator for additional arguments to mach subcommands.

    This decorator should be used to add arguments to mach commands. Arguments
    to the decorator are proxied to ArgumentParser.add_argument().

    For example:

        @Command('foo', help='Run the foo action')
        @CommandArgument('-b', '--bar', action='store_true', default=False,
            help='Enable bar mode.')
        def foo(self):
            pass
    """
    def __init__(self, *args, **kwargs):
        self._command_args = (args, kwargs)

    def __call__(self, func):
        command_args = getattr(func, '_mach_command_args', [])

        command_args.append(self._command_args)

        func._mach_command_args = command_args

        return func


class BaseMixin(object):
    def __init__(self, cwd, settings, log_manager):
        self.cwd = cwd
        self.settings = settings
        self.log_manager = log_manager

        self.logger = logging.getLogger(__name__)

    def log(self, level, action, params, format_str):
        self.logger.log(level, format_str,
            extra={'action': action, 'params': params})

    def _run_command(self, args=None, cwd=None, append_env=None,
        explicit_env=None, log_name=None, log_level=logging.INFO,
        line_handler=None, require_unix_environment=False,
        ignore_errors=False, ignore_children=False, use_stdout_encoding=True,
        output_encoding='UTF-8'):
        """Runs a single command to completion.

        Takes a list of arguments to run where the first item is the
        executable. Runs the command in the specified directory and
        with optional environment variables.

        append_env -- Dict of environment variables to append to the current
            set of environment variables.
        explicit_env -- Dict of environment variables to set for the new
            process. Any existing environment variables will be ignored.

        require_unix_environment if True will ensure the command is executed
        within a UNIX environment. Basically, if we are on Windows, it will
        execute the command via an appropriate UNIX-like shell.

        ignore_children is proxied to mozprocess's ignore_children.
        """
        args = self._normalize_command(args, require_unix_environment)

        self.log(logging.INFO, 'process', {'args': args}, ' '.join(args))

        def handleLine(line):
            # Converts str to unicode on Python 2 and bytes to str on Python 3.
            if isinstance(line, bytes):
                line = line.decode(sys.stdout.encoding or output_encoding,
                    'replace')

            if line_handler:
                line_handler(line)

            if not log_name:
                return

            self.log(log_level, log_name, {'line': line.strip()}, '{line}')

        use_env = {}
        if explicit_env:
            use_env = explicit_env
        else:
            use_env.update(os.environ)

            if append_env:
                use_env.update(append_env)

        self.log(logging.DEBUG, 'process', {'env': use_env}, 'Environment: {env}')

        p = ProcessHandlerMixin(args, cwd=cwd, env=use_env,
            processOutputLine=[handleLine], universal_newlines=True,
            ignore_children=ignore_children)
        p.run()
        p.processOutput()
        status = p.wait()

        if status != 0 and not ignore_errors:
            raise Exception('Process executed with non-0 exit code: %s' % args)

        return status

    def _normalize_command(self, args, require_unix_environment):
        """Adjust command arguments to run in the necessary environment.

        This exists mainly to facilitate execution of programs requiring a *NIX
        shell when running on Windows. The caller specifies whether a shell
        environment is required. If it is and we are running on Windows but
        aren't running in the UNIX-like msys environment, then we rewrite the
        command to execute via a shell.
        """
        assert isinstance(args, list) and len(args)

        if not require_unix_environment or not _in_msys:
            return args

        # Always munge Windows-style into Unix style for the command.
        prog = args[0].replace('\\', '/')

        # PyMake removes the C: prefix. But, things seem to work here
        # without it. Not sure what that's about.

        # We run everything through the msys shell. We need to use
        # '-c' and pass all the arguments as one argument because that is
        # how sh works.
        cline = subprocess.list2cmdline([prog] + args[1:])
        return [_current_shell, '-c', cline]

