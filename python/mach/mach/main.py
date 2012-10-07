# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This module provides functionality for the command-line build tool
# (mach). It is packaged as a module because everything is a library.

from __future__ import unicode_literals

import argparse
import codecs
import imp
import logging
import os
import sys
import traceback

from mach.logger import LoggingManager
from mach.registrar import populate_argument_parser


# Settings for argument parser that don't get proxied to sub-module. i.e. these
# are things consumed by the driver itself.
CONSUMED_ARGUMENTS = [
    'settings_file',
    'verbose',
    'logfile',
    'log_interval',
    'command',
    'cls',
    'method',
    'func',
]

MODULES_SCANNED = False

MACH_ERROR = r'''
The error occurred in mach itself. This is likely a bug in mach itself or a
fundamental problem with a loaded module.

Please consider filing a bug against mach by going to the URL:

    https://bugzilla.mozilla.org/enter_bug.cgi?product=Core&component=mach

'''.lstrip()

ERROR_FOOTER = r'''
If filing a bug, please include the full output of mach, including this error
message.

The details of the failure are as follows:
'''.lstrip()

COMMAND_ERROR = r'''
The error occurred in the implementation of the invoked mach command.

This should never occur and is likely a bug in the implementation of that
command. Consider filing a bug for this issue.
'''.lstrip()

MODULE_ERROR = r'''
The error occured in code that was called by the mach command. This is either
a bug in the called code itself or in the way that mach is calling it.

You should consider filing a bug for this issue.
'''.lstrip()


class ArgumentParser(argparse.ArgumentParser):
    """Custom implementation argument parser to make things look pretty."""

    def error(self, message):
        """Custom error reporter to give more helpful text on bad commands."""
        if not message.startswith('argument command: invalid choice'):
            argparse.ArgumentParser.error(self, message)
            assert False

        print('Invalid command specified. The list of commands is below.\n')
        self.print_help()
        sys.exit(1)

    def format_help(self):
        text = argparse.ArgumentParser.format_help(self)

        # Strip out the silly command list that would preceed the pretty list.
        #
        # Commands:
        #   {foo,bar}
        #     foo  Do foo.
        #     bar  Do bar.
        search = 'Commands:\n  {'
        start = text.find(search)

        if start != -1:
            end = text.find('}\n', start)
            assert end != -1

            real_start = start + len('Commands:\n')
            real_end = end + len('}\n')

            text = text[0:real_start] + text[real_end:]

        return text


class Mach(object):
    """Contains code for the command-line `mach` interface."""

    USAGE = """%(prog)s [global arguments] command [command arguments]

mach (German for "do") is the main interface to the Mozilla build system and
common developer tasks.

You tell mach the command you want to perform and it does it for you.

Some common commands are:

    %(prog)s build     Build B2G.
    %(prog)s help      Show full help, including the list of all commands.

To see more help for a specific command, run:

  %(prog)s <command> --help
"""

    def __init__(self, cwd):
        global MODULES_SCANNED

        assert os.path.isdir(cwd)

        self.cwd = cwd
        self.log_manager = LoggingManager()
        self.logger = logging.getLogger(__name__)

        self.log_manager.register_structured_logger(self.logger)

        mach_logger = logging.getLogger('mach')
        self.log_manager.register_structured_logger(mach_logger)

        if not MODULES_SCANNED:
            self._load_modules()

        MODULES_SCANNED = True

    def run(self, argv, stdin=None, stdout=None, stderr=None):
        """Runs mach with arguments provided from the command line.

        Returns the integer exit code that should be used. 0 means success. All
        other values indicate failure.
        """

        # If no encoding is defined, we default to UTF-8 because without this
        # Python 2.7 will assume the default encoding of ASCII. This will blow
        # up with UnicodeEncodeError as soon as it encounters a non-ASCII
        # character in a unicode instance. We simply install a wrapper around
        # the streams and restore once we have finished.
        stdin = sys.stdin if stdin is None else stdin
        stdout = sys.stdout if stdout is None else stdout
        stderr = sys.stderr if stderr is None else stderr

        orig_stdin = sys.stdin
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr

        sys.stdin = stdin
        sys.stdout = stdout
        sys.stderr = stderr

        try:
            if stdin.encoding is None:
                sys.stdin = codecs.getreader('utf-8')(stdin)

            if stdout.encoding is None:
                sys.stdout = codecs.getwriter('utf-8')(stdout)

            if stderr.encoding is None:
                sys.stderr = codecs.getwriter('utf-8')(stderr)

            return self._run(argv)
        except KeyboardInterrupt:
            print('mach interrupted by signal or user action. Stopping.')
            return 1

        except Exception as e:
            # _run swallows exceptions in invoked handlers and converts them to
            # a proper exit code. So, the only scenario where we should get an
            # exception here is if _run itself raises. If _run raises, that's a
            # bug in mach (or a loaded command module being silly) and thus
            # should be reported differently.
            self._print_error_header(argv, sys.stdout)
            print(MACH_ERROR)

            exc_type, exc_value, exc_tb = sys.exc_info()
            stack = traceback.extract_tb(exc_tb)

            self._print_exception(sys.stdout, exc_type, exc_value, stack)

            return 1

        finally:
            sys.stdin = orig_stdin
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

    def _run(self, argv):
        parser = self.get_argument_parser()

        if not len(argv):
            # We don't register the usage until here because if it is globally
            # registered, argparse always prints it. This is not desired when
            # running with --help.
            parser.usage = Mach.USAGE
            parser.print_usage()
            return 0

        if argv[0] == 'help':
            parser.print_help()
            return 0

        args = parser.parse_args(argv)

        # Add JSON logging to a file if requested.
        if args.logfile:
            self.log_manager.add_json_handler(args.logfile)

        # Up the logging level if requested.
        log_level = logging.INFO
        if args.verbose:
            log_level = logging.DEBUG

        # Always enable terminal logging. The log manager figures out if we are
        # actually in a TTY or are a pipe and does the right thing.
        self.log_manager.add_terminal_logging(level=log_level,
            write_interval=args.log_interval)

        stripped = {k: getattr(args, k) for k in vars(args) if k not in
            CONSUMED_ARGUMENTS}

        # If the command is associated with a class, instantiate and run it.
        # All classes must be Base-derived and take the expected argument list.
        if hasattr(args, 'cls'):
            cls = getattr(args, 'cls')
            instance = cls(self.cwd, None, self.log_manager)
            fn = getattr(instance, getattr(args, 'method'))

        # If the command is associated with a function, call it.
        elif hasattr(args, 'func'):
            fn = getattr(args, 'func')
        else:
            raise Exception('Dispatch configuration error in module.')

        try:
            result = fn(**stripped)

            if not result:
                result = 0

            assert isinstance(result, int)

            return result
        except KeyboardInterrupt as ki:
            raise ki
        except Exception as e:
            exc_type, exc_value, exc_tb = sys.exc_info()

            # The first frame is us and is never used.
            stack = traceback.extract_tb(exc_tb)[1:]

            # Split the frames into those from the module containing the
            # command and everything else.
            command_frames = []
            other_frames = []

            initial_file = stack[0][0]

            for frame in stack:
                if frame[0] == initial_file:
                    command_frames.append(frame)
                else:
                    other_frames.append(frame)

            # If the exception was in the module providing the command, it's
            # likely the bug is in the mach command module, not something else.
            # If there are other frames, the bug is likely not the mach
            # command's fault.
            self._print_error_header(argv, sys.stdout)

            if len(other_frames):
                print(MODULE_ERROR)
            else:
                print(COMMAND_ERROR)

            self._print_exception(sys.stdout, exc_type, exc_value, stack)

            return 1

    def log(self, level, action, params, format_str):
        """Helper method to record a structured log event."""
        self.logger.log(level, format_str,
            extra={'action': action, 'params': params})

    def _load_modules(self):
        """Scan over Python modules looking for mach command providers."""

        # Create parent module otherwise Python complains when the parent is
        # missing.
        if b'mach.commands' not in sys.modules:
            mod = imp.new_module(b'mach.commands')
            sys.modules[b'mach.commands'] = mod

        for path in sys.path:
            # We only support importing .py files from directories.
            commands_path = os.path.join(path, 'mach', 'commands')

            if not os.path.isdir(commands_path):
                continue

            # We only support loading modules in the immediate mach.commands
            # module, not sub-modules. Walking the tree would be trivial to
            # implement if it were ever desired.
            for f in sorted(os.listdir(commands_path)):
                if not f.endswith('.py') or f == '__init__.py':
                    continue

                full_path = os.path.join(commands_path, f)
                module_name = 'mach.commands.%s' % f[0:-3]

                imp.load_source(module_name, full_path)

    def _print_error_header(self, argv, fh):
        fh.write('Error running mach:\n\n')
        fh.write('    ')
        fh.write(repr(argv))
        fh.write('\n\n')

    def _print_exception(self, fh, exc_type, exc_value, stack):
        fh.write(ERROR_FOOTER)
        fh.write('\n')

        for l in traceback.format_exception_only(exc_type, exc_value):
            fh.write(l)

        fh.write('\n')
        for l in traceback.format_list(stack):
            fh.write(l)

    def get_argument_parser(self):
        """Returns an argument parser for the command-line interface."""

        parser = ArgumentParser(add_help=False,
            usage='%(prog)s [global arguments] command [command arguments]')

        # Order is important here as it dictates the order the auto-generated
        # help messages are printed.
        subparser = parser.add_subparsers(dest='command', title='Commands')
        parser.set_defaults(command='help')

        global_group = parser.add_argument_group('Global Arguments')

        global_group.add_argument('-h', '--help', action='help',
            help='Show this help message and exit.')

        global_group.add_argument('-v', '--verbose', dest='verbose',
            action='store_true', default=False,
            help='Print verbose output.')
        global_group.add_argument('-l', '--log-file', dest='logfile',
            metavar='FILENAME', type=argparse.FileType('ab'),
            help='Filename to write log data to.')
        global_group.add_argument('--log-interval', dest='log_interval',
            action='store_true', default=False,
            help='Prefix log line with interval from last message rather '
                'than relative time. Note that this is NOT execution time '
                'if there are parallel operations.')

        populate_argument_parser(subparser)

        return parser
