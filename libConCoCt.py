#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""
Allows to automatically build and test a C program inside a docker container.

Dependencies:
 - python3
 - docker
 - docker-py (>= 1.3.0)
 - cppcheck
 - cunit
 - gcc
"""


import sys
import re
import os
import argparse
import subprocess
import xml.etree.ElementTree
from io import BytesIO
import tarfile
import tempfile
import docker


__version__ = '0.1.0'


class Report(object):
    def __init__(self):
        self.parts = []

    def add_part(self, report_part):
        self.parts.append(report_part)

    def __str__(self):
        ret = ""
        for p in self.parts:
            ret += str(p)
        return ret


class ReportPart(object):
    def __init__(self, source, returncode, messages):
        self.source = source
        self.returncode = returncode
        self.messages = messages

    def __str__(self):
        ret = "{} {}\n".format(self.source, self.returncode)
        for m in self.messages:
            ret += "  " + str(m) + "\n"
        return ret


class Message(object):
    def __init__(self, _type, _file, line, desc):
        self.type = _type
        self.file = _file
        self.line = line
        self.desc = desc

    def __str__(self):
        return "{} {}:{} {}...".format(self.type, self.file, self.line, self.desc[:40])


class CompilerGccParser(object):
    gcc_patterns = [{"type": "ignore",  "file": None, "line": None, "desc": None, "pattern": r"""(.*?):(\d+):(\d+:)? .*\(Each undeclared identifier is reported only once.*"""},
                    {"type": "ignore",  "file": None, "line": None, "desc": None, "pattern": r"""(.*?):(\d+):(\d+:)? .*for each function it appears in.\).*"""},
                    {"type": "ignore",  "file": None, "line": None, "desc": None, "pattern": r"""(.*?):(\d+):(\d+:)? .*this will be reported only once per input file.*"""},
                    {"type": "error",   "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)? [Ee]rror: ([`'"](.*)['"] undeclared .*)"""},
                    {"type": "error",   "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)? [Ee]rror: (conflicting types for .*[`'"](.*)['"].*)"""},
                    {"type": "error",   "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)? (parse error before.*[`'"](.*)['"].*)"""},
                    {"type": "warning", "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)? [Ww]arning: ([`'"](.*)['"] defined but not used.*)"""},
                    {"type": "warning", "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)? [Ww]arning: (conflicting types for .*[`'"](.*)['"].*)"""},
                    {"type": "warning", "file": 0,    "line": 1,    "desc": 4,    "pattern": r"""(.*?):(\d+):(\d+:)? ([Ww]arning:)?\s*(the use of [`'"](.*)['"] is dangerous, better use [`'"](.*)['"].*)"""},
                    {"type": "info",    "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)?\s*(.*((instantiated)|(required)) from .*)"""},
                    {"type": "error",   "file": 0,    "line": 1,    "desc": 6,    "pattern": r"""(.*?):(\d+):(\d+:)?\s*(([Ee]rror)|(ERROR)): (.*)"""},
                    {"type": "warning", "file": 0,    "line": 1,    "desc": 6,    "pattern": r"""(.*?):(\d+):(\d+:)?\s*(([Ww]arning)|(WARNING)): (.*)"""},
                    {"type": "info",    "file": 0,    "line": 1,    "desc": 8,    "pattern": r"""(.*?):(\d+):(\d+:)?\s*(([Nn]ote)|(NOTE)|([Ii]nfo)|(INFO)): (.*)"""},
                    {"type": "error",   "file": 0,    "line": 1,    "desc": 3,    "pattern": r"""(.*?):(\d+):(\d+:)? (.*)"""}]
    ld_patterns =  [{"type": "ignore",  "file": 0,    "line": None, "desc": 2,    "pattern": r"""(.*?):?(\(\.\w+\+.*\))?:\s*(In function [`'"](.*)['"]:)"""},
                    {"type": "warning", "file": 0,    "line": 1,    "desc": 4,    "pattern": r"""(.*?):(\d+):(\d+:)? ([Ww]arning:)?\s*(the use of [`'"](.*)['"] is dangerous, better use [`'"](.*)['"].*)"""},
                    {"type": "warning", "file": 0,    "line": None, "desc": 1,    "pattern": r"""(.*?):?\(\.\w+\+.*\): [Ww]arning:? (.*)"""},
                    {"type": "error",   "file": 0,    "line": None, "desc": 1,    "pattern": r"""(.*?):?\(\.\w+\+.*\): (.*)"""},
                    {"type": "warning", "file": None, "line": None, "desc": 2,    "pattern": r"""(.*[/\\])?ld(\.exe)?: [Ww]arning:? (.*)"""},
                    {"type": "error",   "file": None, "line": None, "desc": 2,    "pattern": r"""(.*[/\\])?ld(\.exe)?: (.*)"""}]
    for p in gcc_patterns:
        p["cpattern"] = re.compile(p["pattern"])
    for p in ld_patterns:
        p["cpattern"] = re.compile(p["pattern"])

    def parse(self, data):
        messages = []
        for l in data.split('\n'):
            for p in CompilerGccParser.gcc_patterns:
                match = p["cpattern"].match(l)
                if match is not None:
                    groups = match.groups()
                    _type = p["type"]
                    _file = None if p["file"] is None else groups[p["file"]]
                    line  = None if p["line"] is None else groups[p["line"]]
                    desc  = None if p["desc"] is None else groups[p["desc"]]
                    m = Message(_type=_type, _file=_file, line=line, desc=desc)
                    messages.append(m)
            for p in CompilerGccParser.ld_patterns:
                match = p["cpattern"].match(l)
                if match is not None:
                    groups = match.groups()
                    _type = p["type"]
                    _file = None if p["file"] is None else groups[p["file"]]
                    line  = None if p["line"] is None else groups[p["line"]]
                    desc  = None if p["desc"] is None else groups[p["desc"]]
                    m = Message(_type=_type, _file=_file, line=line, desc=desc)
                    messages.append(m)
        return messages


class CompilerGcc(object):
    def __init__(self, flags=None):
        if flags is None:
            flags = ["-static", "-std=c99", "-O0", "-g", "-Wall", "-Wextra"]
        self.flags = flags
        self.parser = CompilerGccParser()

    def compile(self, project):
        cmd  = ["gcc"]
        cmd += self.flags
        cmd += ["-fmessage-length=0"]
        cmd += ["-I{project_include}".format(project_include=project.target)]
        cmd += ["-I{include}".format(include=include) for include in project.include]
        cmd += ["-o", os.path.join(project.tempdir, project.target)]
        cmd += project.file_list
        cmd += ["-lcunit"]
        cmd += ["-l{lib}".format(lib=lib) for lib in project.libs]

        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        messages = self.parser.parse(errs)
        return ReportPart("gcc", proc.returncode, messages)


class CppCheckParser(object):
    def parse(self, data):
        # severity: error, warning, style, performance, portability, information
        # location: multiple locations possible, first is primary
        messages = []
        tree = xml.etree.ElementTree.fromstring(data)
        errors = tree.findall('errors/error')
        for e in errors:
            locations = e.findall('location')
            _file = ""
            line  = ""
            for l in locations:
                _file = l.attrib["file"]
                line  = l.attrib["line"]
                # first location is primary
                break
            messages.append(Message(_type=e.attrib["severity"], _file=_file, line=line, desc=e.attrib["verbose"]))
        return messages


class CppCheck(object):
    def __init__(self):
        self.parser = CppCheckParser()

    def check(self, project):
        cmd  = ["cppcheck"]
        cmd += ["-I{include}".format(include=include) for include in project.include]
        cmd += ["--std=c99", "--enable=all", "--xml-version=2"]
        cmd += project.file_list

        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        messages = self.parser.parse(errs)
        return ReportPart("cppcheck", proc.returncode, messages)


class CunitParser(object):
    def parse(self, data):
        messages = []
        tree = xml.etree.ElementTree.fromstring(data)
        suites = tree.findall('CUNIT_RESULT_LISTING/CUNIT_RUN_SUITE')
        for s in suites:
            failure = s.find('CUNIT_RUN_SUITE_FAILURE')
            success = s.find('CUNIT_RUN_SUITE_SUCCESS')
            if failure is not None:
                s_result = False
                s = failure
            elif success is not None:
                s_result = True
                s = success
            else:
                assert(0)
            s_name = s.find('SUITE_NAME').text
            tests = s.findall('CUNIT_RUN_TEST_RECORD')
            for t in tests:
                test = None
                t_failure = t.find('CUNIT_RUN_TEST_FAILURE')
                t_success = t.find('CUNIT_RUN_TEST_SUCCESS')
                if t_failure is not None:
                    t_name = t_failure.find('TEST_NAME').text
                    t_file = t_failure.find('FILE_NAME').text
                    t_line = t_failure.find('LINE_NUMBER').text
                    t_cond = t_failure.find('CONDITION').text
                    messages.append(Message(_type="error", _file=t_file, line=t_line, desc="{suite} - {test} - Condition: {cond}".format(suite=s_name, test=t_name, cond=t_cond)))
                elif t_success is not None:
                    t_name = t_success.find('TEST_NAME').text
                else:
                    assert(0)
        return messages


class CunitChecker(object):
    def __init__(self):
        self.parser = CunitParser()
        self.client = docker.Client(version="1.17")
        self.client.info()

    def run(self, project):
        img = "autotest/img_" + project.target

        dockerfile = """FROM scratch
                        COPY {target} /
                        CMD ["/{target}"]
                     """

        with open(os.path.join(project.tempdir, "Dockerfile"), "w") as fd:
            fd.write(dockerfile.format(target=project.target))
        build_out = self.client.build(path=project.tempdir, tag=img, rm=True, stream=False)
        [_ for _ in build_out]

        cont = self.client.create_container(image=img)
        self.client.start(container=cont)

        #out = self.client.attach(container=cont, logs=True)
        #print(out.decode('utf-8'))

        self.client.wait(container=cont)

        temp = self.client.copy(container=cont, resource="/CUnitAutomated-Results.xml")
        buffer = BytesIO()
        buffer.write(temp.data)
        buffer.seek(0)
        tar = tarfile.open(fileobj=buffer, mode='r')
        fd = tar.extractfile('CUnitAutomated-Results.xml')
        data = fd.read()
        fd.close()
        tar.close()

        self.client.stop(container=cont)
        self.client.remove_container(container=cont)
        self.client.remove_image(image=img)

        messages = self.parser.parse(data)
        return ReportPart("cunit", 0, messages)


class Project(object):
    cb_project_template = """
        <?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
        <CodeBlocks_project_file>
	        <FileVersion major="1" minor="6" />
	        <Project>
		        <Option title="{title}" />
		        <Option compiler="gcc" />
		        <Build>
			        <Target title="Debug">
				        <Option output="{title}" prefix_auto="1" extension_auto="1" />
				        <Option type="1" />
				        <Option compiler="gcc" />
				        <Compiler>
					        <Add option="-g" />
				        </Compiler>
			        </Target>
		        </Build>
		        <Compiler>
			        <Add option="-Wall" />
		        </Compiler>
		        {units}
	        </Project>
        </CodeBlocks_project_file>
        <!--Watermark user="dummy" TODO: sadly, codeblocks removes this... -->
    """

    cb_unit_template = """<Unit filename="{filename}"><Option compilerVar="CC" /></Unit>"""

    cb_unit_h_template = """<Unit filename="{filename}" />"""


    def __init__(self, target, file_list, libs=None, includes=None):
        if libs is None:
            libs = []
        if includes is None:
            includes = []
        self.target    = target
        self.file_list = file_list
        self.libs      = libs
        self.include   = includes
        self.tempdir   = None

        # TODO: test if libs are installed?!
        # TODO: check if files exist!

    def create_cb_project(self):
        unit_str = ""
        for f in self.file_list:
            unit_str += self.cb_unit_template.format(filename=f)
        import glob
        for d in self.include:
            for f in glob.glob(d + "/*.h"):
                unit_str += self.cb_unit_h_template.format(filename=f)
        # TODO: implement pretty much everything...
        with open("temp.cbp", "w") as fd:
            fd.write(self.cb_project_template.format(title=self.target, units=unit_str))


class Excercise(object):
    def __init__(self):
        pass


class Solution(object):
    def __init__(self):
        pass


class ConCoCt(object):
    def __init__(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.check_env()

    def __del__(self):
        self.tempdir.cleanup()

    def check_env(self):
        # gcc
        try:
            subprocess.call(["gcc", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError("gcc not found!")
        # cppcheck
        try:
            subprocess.call(["cppcheck", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError("cppcheck not found!")
        # docker
        try:
            proc = subprocess.call(["docker", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError("docker not found!")
        if proc != 0:
            raise FileNotFoundError("docker found but permission denied. Is user in group 'docker'?")
        # cunit
        try:
            proc = subprocess.call(["ld", "-lcunit", "-o{tmpfile}".format(tmpfile=os.path.join(self.tempdir.name, "__ld_check.out"))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError("ld not found!")
        if proc != 0:
            raise FileNotFoundError("cunit not found!")
        # docker-py
        version_info = tuple([int(d) for d in docker.version.split("-")[0].split(".")])
        if version_info[0] < 1 or version_info[0] == 1 and version_info[1] < 3:
            raise FileNotFoundError("docker-py version to old!")

    def check_project(self, project):
        # TODO: maybe move temp dir to solution class
        project.tempdir = self.tempdir.name

        r = Report()
        _r = CppCheck().check(project)
        r.add_part(_r)
        _r = CompilerGcc().compile(project)
        r.add_part(_r)
        # TODO: run cunit only, if compile successful
        _r = CunitChecker().run(project)
        r.add_part(_r)

        project.tempdir = None
        return r


def parse_args():
    parser = argparse.ArgumentParser(description='Simple gcc wrapper.')
    parser.add_argument('--version', action='version', version='%(prog)s ' + __version__)
    cmd_options = parser.parse_args()


if __name__ == '__main__':
    parse_args()

    try:
        w = ConCoCt()
    except FileNotFoundError as e:
        sys.exit(e)

    p = Project("task1", ["task1/main.c", "task1/group1/lib.c"], libs=["m"], includes=["task1"])
    p.create_cb_project()
    r = w.check_project(p)
    print(r)

#
# task          -> Eine Aufgabe
#   submission  -> Eine Abgabe
#
#
#
#
#
#{
#    "name":        "Schaltjahr",
#    "description": "description.md",
#    "libs":        "
#}
