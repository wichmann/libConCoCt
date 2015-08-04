
"""
Contains a class to run CppCheck on a projects source files and parse the
results as Messages in a Report.

Authors: Martin Wichmann, Christian Wichmann
"""

import subprocess
import xml.etree.ElementTree

from .report import Message
from .report import ReportPart


class CppCheckParser(object):
    def parse(self, data):
        # severity: error, warning, style, performance, portability, information
        # location: multiple locations possible, first is primary
        messages = []
        tree = xml.etree.ElementTree.fromstring(data)
        errors = tree.findall('errors/error')
        for e in errors:
            locations = e.findall('location')
            _file = ''
            line  = ''
            for l in locations:
                _file = l.attrib['file']
                line  = l.attrib['line']
                # first location is primary
                break
            messages.append(Message(_type=e.attrib['severity'], _file=_file, line=line, desc=e.attrib['verbose']))
        return messages


class CppCheck(object):
    def __init__(self):
        self.parser = CppCheckParser()

    def check(self, project):
        cmd  = ['cppcheck']
        # do not let CppCheck complain when it is to stupid to find systems includes
        cmd += ['--suppress=missingIncludeSystem']
        cmd += ['-I{include}'.format(include=include) for include in project.include]
        cmd += ['--std=c99', '--enable=all', '--xml-version=2']
        cmd += project.file_list

        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        messages = self.parser.parse(errs)
        return ReportPart('cppcheck', proc.returncode, messages)



