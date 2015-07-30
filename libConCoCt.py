#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""
Allows to automatically build and test a C program inside a docker container.

To run this script you have to have either root privledges or be in the group
"docker". Use the following command to add your user to that group:

    $ sudo usermod -aG docker [your user]

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
from collections import defaultdict
import tarfile
import tempfile
import docker
import json
import glob
import hashlib
import base64
from zipfile import ZipFile
import tempfile


__version__ = '0.1.0'


class ReportJSONEncoder(json.JSONEncoder):
    """
    Converts reports, report parts and messages into JSON strings. The default
    method returns a serializable object for all three classes containing report
    data. Every time either a report, a part of a report or a message has to be
    serialized to JSON, this encoder can be used:

    >>> json.dumps(some_report, default=ReportJSONEncoder)
    {"gcc": {"messages": [{"type": "", "line": "", "desc": "", "file": ""}, ...], "returncode": 0}, ...}
    """
    # TODO Write JSONDecoder.
    def default(self, obj):
        if isinstance(obj, Report):
            report_object = {}
            for report in obj.parts:
                report_object[report.source] = ReportJSONEncoder().default(report)
            return report_object
        elif isinstance(obj, ReportPart):
            report_part_object = {}
            report_part_object['returncode'] = obj.returncode
            report_part_object['messages'] = [ReportJSONEncoder().default(m) for m in obj.messages]
            return report_part_object
        elif isinstance(obj, Message):
            message_part_object = {}
            # get all information from message object (all fields that are not inherited by object class)
            message_infos = filter(lambda x: x not in object.__dict__ , obj.__dict__.keys())
            for info in message_infos:
                message_part_object[info] = obj.__getattribute__(info)
            return message_part_object
        else:
            return JSONEncoder.default(self, obj)


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

    def to_json(self):
        """
        Converts data from this report to JSON format. First all data from
        report parts and their messages are collected as dictionary. Then the
        whole dictionary can be dumped to JSON and be returned.

        :returns: string containing a JSON representation of this report
        """
        return json.dumps(self, cls=ReportJSONEncoder)

    def to_xml(self):
        """
        Builds a XML representation of all report parts in this report and all
        messages inside these parts.

        :returns: string containing XML representation of this report
        """
        # TODO Check if some serialization library like pyxser would be better.
        report_root = xml.etree.ElementTree.Element('report')
        for part in self.parts:
            report_root.append(part.to_xml())
        return xml.etree.ElementTree.tostring(report_root)


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

    def to_json(self):
        """
        Converts data from this report part to JSON format. This includes all
        messages inside this part and the return code.

        :returns: string containing a JSON representation of this report part
        """
        return json.dumps(self, cls=ReportJSONEncoder)

    def to_xml(self):
        """
        Builds a XML representation of this report part. It returns always the
        XML Element containing all data of this part.
        """
        attributes = {'returncode': str(self.returncode)}
        current_part = xml.etree.ElementTree.Element(self.source, attrib=attributes)
        # create sub-element for each message in report part
        for message in self.messages:
            current_part.append(message.to_xml())
        return current_part


class Message(object):
    def __init__(self, _type, _file, line, desc):
        self.type = _type
        self.file = _file
        self.line = line
        self.desc = desc

    def __str__(self):
        return "{} {}:{} {}...".format(self.type, self.file, self.line, self.desc[:40])

    def to_json(self):
        """
        Converts data from this message to JSON format. This includes at least
        the type, file name, line number and a description.

        :returns: string containing a JSON representation of this message
        """
        return json.dumps(self, cls=ReportJSONEncoder)

    def to_xml(self):
        """
        Builds a XML representation of this message. It returns always the XML
        Element containing all data of this message.
        """
        message_element = xml.etree.ElementTree.Element('message')
        # get all information from message object (all fields that are not inherited by object class)
        message_infos = filter(lambda x: x not in object.__dict__ , self.__dict__.keys())
        # append all messages as sub-elements
        for info in message_infos:
            new_sub_element = xml.etree.ElementTree.SubElement(message_element, info)
            new_sub_element.text = self.__getattribute__(info)
        return message_element


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
#        cmd += ["-I{project_include}".format(project_include=project.target)]
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
        # do not let CppCheck complain when it is to stupid to find systems includes
        cmd += ["--suppress=missingIncludeSystem"]
        cmd += ["-I{include}".format(include=include) for include in project.include]
        cmd += ["--std=c99", "--enable=all", "--xml-version=2"]
        cmd += project.file_list

        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        messages = self.parser.parse(errs)
        return ReportPart("cppcheck", proc.returncode, messages)


class CunitParser(object):
    """
    Parses the output of a CUnit test run and returns messages containing the
    not successfully completed tests. The messages can be appended onto a
    Report object together with the results from CppCheck and Compiler.

    Furthermore, a dictionary with all tests from all suites that have been run
    is available as the attribute "list_of_tests".
    """
    def __init__(self):
        self.list_of_tests = defaultdict(dict)

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
                    messages.append(Message(_type="error", _file=t_file, line=t_line,
                                            desc="{suite} - {test} - Condition: {cond}".format(suite=s_name, test=t_name, cond=t_cond)))
                    self.add_test_result(s_name, t_name, False)
                elif t_success is not None:
                    t_name = t_success.find('TEST_NAME').text
                    self.add_test_result(s_name, t_name, True)
                else:
                    assert(0)
        return messages

    def add_test_result(self, suite_name, test_name, success=False):
        """
        Adds a single unit test result to the list of all tests in all suites
        that have been run. After parsing of the data is complete that list
        contains all results.

        :param suite_name: name of test suite for which to add result
        :param test_name: name of unit test for which to add result
        :param success: whether the unit test in test suite has been successful
        """
        self.list_of_tests[suite_name][test_name] = success


class CunitChecker(object):
    def __init__(self):
        self.parser = CunitParser()
        self.client = docker.Client(version="1.17")
        self.client.info()

    def run(self, project):
        img = "autotest/" + project.target
        # check whether target file exists (has been compiled correctly)
        if not os.path.exists(os.path.join(project.tempdir, project.target)):
            raise FileNotFoundError("Error: Executable file has not been created!")
        dockerfile = """FROM scratch
                        COPY {target} /
                        CMD ["/{target}"]
                     """
        # build Dockerfile and Docker image
        # TODO: this should be possible in-memory
        with open(os.path.join(project.tempdir, "Dockerfile"), "w") as fd:
            fd.write(dockerfile.format(target=project.target))
        build_out = self.client.build(path=project.tempdir, tag=img, rm=True, stream=False)
        [_ for _ in build_out]

        # create container and start it (start unit tests, see Dockerfile)
        # TODO: check if image was created
        cont = self.client.create_container(image=img)
        self.client.start(container=cont)
        #out = self.client.attach(container=cont, logs=True)
        #print(out.decode('utf-8'))
        ret_val = self.client.wait(container=cont)
        # catch problem when unit test executable returns with error code
        if ret_val != 0:
            print('Error code returned: {}'.format(ret_val))
            return ReportPart("cunit", ret_val, [])

        try:
            temp = self.client.copy(container=cont, resource="/CUnitAutomated-Results.xml")
        except docker.errors.APIError as e:
            # TODO: is there a better way to check and handle this?!
            if 'Could not find the file' in e.explanation.decode('utf-8'):
                print('Could not extract cunit results. Maybe source does not contain test?!')
            return ReportPart("cunit", -1, [])
        buffer = BytesIO(temp.read())
        with tarfile.open(fileobj=buffer, mode='r') as tar:
            with tar.extractfile('CUnitAutomated-Results.xml') as fd:
                data = fd.read()

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
				        <Option output="Build/{title}_exec" prefix_auto="1" extension_auto="1" />
                        <Option working_dir="" />
				        <Option object_output="Build/" />
				        <Option type="1" />
				        <Option compiler="gcc" />
				        <Compiler>
                            <Add option="-Wall" />
					        <Add option="-g" />
                            <Add option="-std=c99" />
                            {include_dirs}
				        </Compiler>
                        <Linker>
					        <Add library="cunit" />
				        </Linker>
			        </Target>
		        </Build>
		        <Compiler>
			        <Add option="-Wall" />
		        </Compiler>
                <Linker>
					<Add option="-s" />
				</Linker>
		        {units}
	        </Project>
        </CodeBlocks_project_file>
        <!--Watermark user="dummy" TODO: sadly, codeblocks removes this... -->
    """
    cb_layout_template = """
        <?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
        <CodeBlocks_layout_file>
        	<ActiveTarget name="Debug" />
        	<File name="description.md" open="1" top="1" tabpos="1" split="0" active="1" splitpos="0" zoom_1="0" zoom_2="0">
        		<Cursor>
        			<Cursor1 position="0" topLine="0" />
        		</Cursor>
        	</File>
        	<File name="solution.c" open="1" top="0" tabpos="2" split="0" active="1" splitpos="0" zoom_1="0" zoom_2="0">
        		<Cursor>
        			<Cursor1 position="0" topLine="0" />
        		</Cursor>
        	</File>
        </CodeBlocks_layout_file>
    """
    cb_unit_template = """<Unit filename="{filename}"><Option compilerVar="CC" /></Unit>"""
    cb_unit_h_template = """<Unit filename="{filename}" />"""

    def __init__(self, target, file_list, libs=None, includes=None):
        if libs is None:
            libs = []
        if includes is None:
            includes = []
        self.project_name = target
        self.file_list    = file_list
        self.libs         = libs
        self.include      = includes
        self.tempdir      = None

        # Workaround for Docker not handling spaces well. Also upper case
        # characters are a no go! Equal signs (used as padding in Base64) have
        # to be stripped from the because they are not valid in docker repo
        # name! (See: https://github.com/docker/docker/issues/2105)
        self.target = base64.b64encode(self.project_name.encode("utf-8")).decode("utf-8").lower().replace("=", "")

        for f in self.file_list:
            if not os.path.isfile(f):
                raise FileNotFoundError("Source file {} not found!".format(f))

        # TODO: test if libs are installed?!


    def create_cb_project(self, file_name="project.zip"):
        """
        Create a CodeBlocks project inside a ZIP file. A XML project file
        contains links to all source and header files and sets all necessary
        compiler options. Furthermore all include directories are added as
        search directories for the compiler.

        :param file_name: name for ZIP file containing CodeBlocks project
        :returns: name of ZIP file containing CodeBlocks project
        """
        unit_str = ""
        include_dirs = ""
        with ZipFile(file_name, "w") as project_zip:
            already_packed_files = []
            # include all code files
            for f in self.file_list:
                only_file_name = os.path.basename(f)
                project_zip.write(f, only_file_name)
                unit_str += self.cb_unit_template.format(filename=only_file_name)
                already_packed_files.append(f)
            # include all header from all include directories
            for d in self.include:
                # set path to include files for compiler
                #include_dirs += """<Add directory="{dir}" />""".format(dir=d)
                # add all header in include directories in project
                for f in glob.glob(d + "/*.h"):
                    if f not in already_packed_files:
                        only_file_name = os.path.basename(f)
                        project_zip.write(f, only_file_name)
                        unit_str += self.cb_unit_h_template.format(filename=only_file_name)
                        already_packed_files.append(f)
            # include description file
            task_directory = os.path.dirname(os.path.dirname(self.file_list[0]))
            description_file_name = "description.md"
            description_file = os.path.join(task_directory, description_file_name)
            unit_str += self.cb_unit_h_template.format(filename=description_file_name)
            project_zip.write(description_file, description_file_name)
            # include project file
            with tempfile.NamedTemporaryFile() as buffer:
                buffer.write(self.cb_project_template.format(title=self.project_name, units=unit_str,
                                                             include_dirs=include_dirs).encode("utf-8"))
                buffer.flush()
                project_zip.write(buffer.name, "{}.cbp".format(self.project_name))
            # include layout file
            with tempfile.NamedTemporaryFile() as buffer:
                buffer.write(self.cb_layout_template.encode("utf-8"))
                buffer.flush()
                project_zip.write(buffer.name, "{}.layout".format(self.project_name))
        return file_name


class Task(object):
    """
        Represents one Task. Contains all Informations, to create 'packs' of
        files to check, compile or distribute.

        :ivar name          Name of the task.
        :ivar desc          Path to description file.
        :ivar scr_dir       Base dir for all files.
        :ivar files         General files included in all other 'filesets'
        :ivar files_main    Files used for executing.
        :ivar files_test    Files used for testing.
        :ivar files_student Files to be added by the student or for the student in a cb project.
    """

    def __init__(self, path):
        self.path = path
        with open(os.path.join(path, "config.json"), "r") as fd:
            data = json.load(fd)
        self.name          = data["name"]
        self.desc          = data["desc"]
        self.libs          = data["libs"]
        self.src_dir       = data["src_dir"]
        self.files         = data["files"]
        self.files_main    = data["files_main"]
        self.files_test    = data["files_test"]
        self.files_student = data["files_student"]

    def get_main_project(self, solution):
        file_list = []
        file_list += [os.path.join(self.path, self.src_dir, f) for f in self.files]
        file_list += [os.path.join(self.path, self.src_dir, f) for f in self.files_main]
        # add all files of given solution or files that have been defines in config file
        if solution:
            file_list += solution.solution_file_list
        else:
            file_list += [os.path.join(self.path, self.src_dir, f) for f in self.files_student]
        # add all include directories
        include_list = []
        include_list += [os.path.join(self.path, self.src_dir)]
        # TODO: add task includes
        return Project(self.name, file_list, self.libs, include_list)

    def get_test_project(self, solution):
        file_list = []
        file_list += [os.path.join(self.path, self.src_dir, f) for f in self.files]
        file_list += [os.path.join(self.path, self.src_dir, f) for f in self.files_test]
        # add all files of given solution or files that have been defines in config file
        if solution:
            file_list += solution.solution_file_list
        else:
            file_list += [os.path.join(self.path, self.src_dir, f) for f in self.files_student]
        # add all include directories
        include_list = []
        include_list += [os.path.join(self.path, self.src_dir)]
        # TODO: add task includes
        return Project(self.name, file_list, self.libs, include_list)



class Solution(object):
    """
    Provides a data object containing all information about a possible solution
    for a given task. The source files given as parameter will be compiled with
    all source files of the task itself.
    """
    def __init__(self, task, solution_file_list=None):
        self.task = task
        if solution_file_list:
            self.solution_file_list = solution_file_list
        else:
            self.solution_file_list = []

    def get_solution_from_filesystem(self, username):
        """
        Allows the user to automatically collect a solution from filesystem by
        a given task (see __init__()) and a given user name. Base directory for
        the search is the current working directory???
        """
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
            proc = subprocess.call(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        if version_info[0] < 1 or version_info[0] == 1 and version_info[1] < 2:
            raise FileNotFoundError("docker-py version to old!")

    def check_project(self, project):
        # TODO: move temp dir to project class
        project.tempdir = self.tempdir.name

        r = Report()
        _r = CppCheck().check(project)
        r.add_part(_r)
        if _r.returncode == 0:
            _r = CompilerGcc().compile(project)
            r.add_part(_r)
        else:
            print("Error: Could not run compiler because CppCheck returned error code.")
        if _r.returncode == 0:
            checker = CunitChecker()
            _r = checker.run(project)
            self.print_unit_test_results(checker.parser.list_of_tests)
            r.add_part(_r)
        else:
            print("Error: Could not run unit tests because Compiler returned error code.")

        project.tempdir = None
        return r

    def print_unit_test_results(self, testresults):
        """
        Prints test results to console if tests have been successfully executed.

        :param testresults: dictionary containing the results for all test
                            suites and their unit tests
        """
        if testresults:
            print("=====")
            for suite in sorted(testresults):
                print("Suite: {}".format(suite))
                for test in sorted(testresults[suite]):
                    print("{:30s} - {}".format(test, 'success' if testresults[suite][test] else 'failure'))
            print("=====")


def parse_args():
    parser = argparse.ArgumentParser(description='Simple gcc wrapper.')
    parser.add_argument('--version', action='version', version='%(prog)s ' + __version__)
    cmd_options = parser.parse_args()


def find_all_tasks(tasks_path="tasks"):
    tasks = []
    for d in os.listdir(tasks_path):
        try:
            t = Task(os.path.join(tasks_path, d))
            if t is not None:
                tasks.append(t)
        except FileNotFoundError:
            pass
    return tasks


if __name__ == '__main__':
    parse_args()
    try:
        w = ConCoCt()
    except FileNotFoundError as e:
        sys.exit(e)

    t = Task(os.path.join("tasks", "greaterZero"))
    s1 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/solutions/greaterZero/user1/solution.c', ))
    s2 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/solutions/greaterZero/user2/solution.c', ))

    # create test project and unit test it
    #p = t.get_test_project(s2)
    #r = w.check_project(p)
    #print(r)

    # create CodeBlocks project
    p = t.get_main_project(None)
    p.create_cb_project()
