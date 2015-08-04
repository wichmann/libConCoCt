
"""
Contains a frontend for the GCC compiler and a parser to get messages from
standard output of the compiler.

Authors: Martin Wichmann, Christian Wichmann
"""

import re
import os
import subprocess

from .report import Message
from .report import ReportPart


class CompilerGccParser(object):
    gcc_patterns = [{'type': 'ignore',  'file': None, 'line': None, 'desc': None, 'pattern': r"""(.*?):(\d+):(\d+:)? .*\(Each undeclared identifier is reported only once.*"""},
                    {'type': 'ignore',  'file': None, 'line': None, 'desc': None, 'pattern': r"""(.*?):(\d+):(\d+:)? .*for each function it appears in.\).*"""},
                    {'type': 'ignore',  'file': None, 'line': None, 'desc': None, 'pattern': r"""(.*?):(\d+):(\d+:)? .*this will be reported only once per input file.*"""},
                    {'type': 'error',   'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)? [Ee]rror: ([`'"](.*)['"] undeclared .*)"""},
                    {'type': 'error',   'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)? [Ee]rror: (conflicting types for .*[`'"](.*)['"].*)"""},
                    {'type': 'error',   'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)? (parse error before.*[`'"](.*)['"].*)"""},
                    {'type': 'warning', 'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)? [Ww]arning: ([`'"](.*)['"] defined but not used.*)"""},
                    {'type': 'warning', 'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)? [Ww]arning: (conflicting types for .*[`'"](.*)['"].*)"""},
                    {'type': 'warning', 'file': 0,    'line': 1,    'desc': 4,    'pattern': r"""(.*?):(\d+):(\d+:)? ([Ww]arning:)?\s*(the use of [`'"](.*)['"] is dangerous, better use [`'"](.*)['"].*)"""},
                    {'type': 'info',    'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)?\s*(.*((instantiated)|(required)) from .*)"""},
                    {'type': 'error',   'file': 0,    'line': 1,    'desc': 6,    'pattern': r"""(.*?):(\d+):(\d+:)?\s*(([Ee]rror)|(ERROR)): (.*)"""},
                    {'type': 'warning', 'file': 0,    'line': 1,    'desc': 6,    'pattern': r"""(.*?):(\d+):(\d+:)?\s*(([Ww]arning)|(WARNING)): (.*)"""},
                    {'type': 'info',    'file': 0,    'line': 1,    'desc': 8,    'pattern': r"""(.*?):(\d+):(\d+:)?\s*(([Nn]ote)|(NOTE)|([Ii]nfo)|(INFO)): (.*)"""},
                    {'type': 'error',   'file': 0,    'line': 1,    'desc': 3,    'pattern': r"""(.*?):(\d+):(\d+:)? (.*)"""}]
    ld_patterns =  [{'type': 'ignore',  'file': 0,    'line': None, 'desc': 2,    'pattern': r"""(.*?):?(\(\.\w+\+.*\))?:\s*(In function [`'"](.*)['"]:)"""},
                    {'type': 'warning', 'file': 0,    'line': 1,    'desc': 4,    'pattern': r"""(.*?):(\d+):(\d+:)? ([Ww]arning:)?\s*(the use of [`'"](.*)['"] is dangerous, better use [`'"](.*)['"].*)"""},
                    {'type': 'warning', 'file': 0,    'line': None, 'desc': 1,    'pattern': r"""(.*?):?\(\.\w+\+.*\): [Ww]arning:? (.*)"""},
                    {'type': 'error',   'file': 0,    'line': None, 'desc': 1,    'pattern': r"""(.*?):?\(\.\w+\+.*\): (.*)"""},
                    {'type': 'warning', 'file': None, 'line': None, 'desc': 2,    'pattern': r"""(.*[/\\])?ld(\.exe)?: [Ww]arning:? (.*)"""},
                    {'type': 'error',   'file': None, 'line': None, 'desc': 2,    'pattern': r"""(.*[/\\])?ld(\.exe)?: (.*)"""}]
    for p in gcc_patterns:
        p['cpattern'] = re.compile(p['pattern'])
    for p in ld_patterns:
        p['cpattern'] = re.compile(p['pattern'])

    def parse(self, data):
        messages = []
        for l in data.split('\n'):
            for p in CompilerGccParser.gcc_patterns:
                match = p['cpattern'].match(l)
                if match is not None:
                    groups = match.groups()
                    _type = p['type']
                    _file = None if p['file'] is None else groups[p['file']]
                    line  = None if p['line'] is None else groups[p['line']]
                    desc  = None if p['desc'] is None else groups[p['desc']]
                    m = Message(_type=_type, _file=_file, line=line, desc=desc)
                    messages.append(m)
            for p in CompilerGccParser.ld_patterns:
                match = p['cpattern'].match(l)
                if match is not None:
                    groups = match.groups()
                    _type = p['type']
                    _file = None if p['file'] is None else groups[p['file']]
                    line  = None if p['line'] is None else groups[p['line']]
                    desc  = None if p['desc'] is None else groups[p['desc']]
                    m = Message(_type=_type, _file=_file, line=line, desc=desc)
                    messages.append(m)
        return messages


class CompilerGcc(object):
    def __init__(self, flags=None):
        if flags is None:
            flags = ['-static', '-std=c99', '-O0', '-g', '-Wall', '-Wextra']
        self.flags = flags
        self.parser = CompilerGccParser()

    def compile(self, project):
        cmd  = ['gcc']
        cmd += self.flags
        cmd += ['-fmessage-length=0']
        # cmd += ['-I{project_include}'.format(project_include=project.target)]
        cmd += ['-I{include}'.format(include=include) for include in project.include]
        cmd += ['-o', os.path.join(project.tempdir, project.target)]
        cmd += project.file_list
        cmd += ['-lcunit']
        cmd += ['-l{lib}'.format(lib=lib) for lib in project.libs]

        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        messages = self.parser.parse(errs)
        return ReportPart('gcc', proc.returncode, messages)
