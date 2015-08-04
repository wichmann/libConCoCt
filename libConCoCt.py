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
 - paramiko (SSH implementation)
 - cppcheck
 - cunit
 - gcc
"""


import sys
import re
import os
import time
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
from requests.exceptions import ReadTimeout
# imports for VM runner
from paramiko.client import SSHClient
from paramiko import AutoAddPolicy
import posixpath
import stat


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
            if obj.tests:
                report_part_object['tests'] = obj.tests
            return report_part_object
        elif isinstance(obj, Message):
            message_part_object = {}
            # get all information from message object (all fields that are not inherited by object class)
            message_infos = filter(lambda x: x not in object.__dict__ , obj.__dict__.keys())
            for info in message_infos:
                message_part_object[info] = obj.__getattribute__(info)
            return message_part_object
        else:
            return super(ReportJSONEncoder, self).default(obj)


class Report(object):
    def __init__(self):
        self.parts = []

    def add_part(self, report_part):
        self.parts.append(report_part)

    def __str__(self):
        ret = ''
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
    def __init__(self, source, returncode, messages, tests=None):
        self.source = source
        self.returncode = returncode
        self.messages = messages
        self.tests = tests

    def __str__(self):
        ret = '{} {}\n'.format(self.source, self.returncode)
        for m in self.messages:
            ret += '  ' + str(m) + '\n'
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
        # TODO Add test results (self.tests) to XML output!
        return current_part


class Message(object):
    def __init__(self, _type, _file, line, desc):
        self.type = _type
        self.file = _file
        self.line = line
        self.desc = desc

    def __str__(self):
        return '{} {}:{} {}...'.format(self.type, self.file, self.line, self.desc[:40])

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
#        cmd += ['-I{project_include}'.format(project_include=project.target)]
        cmd += ['-I{include}'.format(include=include) for include in project.include]
        cmd += ['-o', os.path.join(project.tempdir, project.target)]
        cmd += project.file_list
        cmd += ['-lcunit']
        cmd += ['-l{lib}'.format(lib=lib) for lib in project.libs]

        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        messages = self.parser.parse(errs)
        return ReportPart('gcc', proc.returncode, messages)


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
        if not data:
            raise ValueError('No data to parse.')
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
                    messages.append(Message(_type='error', _file=t_file, line=t_line,
                                            desc='{suite} - {test} - Condition: {cond}'.format(suite=s_name, test=t_name, cond=t_cond)))
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
    """
    Executes the compiled executable and checks all unit tests. Returned will be
    a XML report by CUnit that can be evaluated later.

    For security, currently a Docker container is used. Possible security
    solutions:
    * Docker container - Not inherently secure, has to be improved with apparmor
      profile and lxc directives.
    * ptrace - Linux kernels system call policy enforcer
    * lxc - Linux container, defines namespaces in kernel for all ressources
      See: https://help.ubuntu.com/lts/serverguide/lxc.html
    * systrace - enforces system call policies based on ptrace backend on Linux
    * VirtualBox - Full blown virtual machine with all its overhead, difficult
      to control from host machine and to get files inside the VM.
      See: http://stackoverflow.com/questions/21324153/how-to-read-files-from-a-virtual-machine-using-python
    * QEMU - Virtual machine
    * KVM, XEN - Kernel based virtualisation, light-weight technique based on
      hypervisor virtualisation.
    * seccomp - Googles solution developed for Chrome, allows one-way transition
      into a "secure" state where it cannot make any system calls except exit(),
      read() and write() to already-open file descriptors. (already in kernel)
    * Fakeroot-ng - wrap all system calls that program performs so that it
      thinks it is running as root.
    * Proot [http://proot.me/]
    * geordi - C++ eval bot, not suitable

    See also:
    * http://stackoverflow.com/questions/4249063/run-an-untrusted-c-program-in-a-sandbox-in-linux-that-prevents-it-from-opening-f
    * http://unix.stackexchange.com/questions/6433/how-to-jail-a-process-without-being-root/6455#6455
    """
    def __init__(self, backend):
        self.parser = CunitParser()
        self.report_name = 'cunit'
        self.backend = backend

    def run(self, project):
        if self.backend == 'docker':
            runner = DockerRunner()
        else:
            runner = VMRunner(shutdown_vm_after=False)
        error_code, data = runner.run(project)
        if error_code:
            return ReportPart(self.report_name, error_code, [])
        else:
            messages = self.parser.parse(data)
            return ReportPart(self.report_name, error_code, messages, self.parser.list_of_tests)


class VirtualBoxControl(object):
    """
    Controls a virtual machine in Oracle VirtualBox on the local host machine
    via command line.

    Alternatively the VM could be controlled via Python ("vbox" or better
    "pyvbox")
    """
    def __init__(self, vm_name, wait_after_boot=20):
        self.vm_name = vm_name
        self.wait_after_boot = wait_after_boot

    def start_VM(self):
        """
        Starts the virtual machine with a given name in VirtualBox on the local
        host machine.

        :returns: True, if the VM has been started sucessfully, otherwise False
        """
        # TODO Reset to last checkpoint.
        # TODO Let VM go to sleep instead of shutting down
        print('Starting VM...')
        if not self.check_VM():
            cmd  = ['VBoxManage']
            cmd += ['startvm']
            cmd += [self.vm_name]
            cmd += ['--type']
            cmd += ['headless']
            proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            outs, errs = proc.communicate()
            if str(outs).count('has been successfully started'):
                print('Waiting', end='', flush=True)
                for _ in range(self.wait_after_boot):
                    print('.', end='', flush=True)
                    time.sleep(1)
                print('\nVM successfully started.')
                return True
            else:
                print('VM could not be started.')
                return False
        return True

    def stop_VM(self):
        cmd  = ['VBoxManage']
        cmd += ['controlvm']
        cmd += [self.vm_name]
        cmd += ['acpipowerbutton']
        return_code = subprocess.call(cmd)
        print('Shutdown: {}'.format(return_code))
        return bool(return_code)

    def check_VM(self):
        cmd  = ['VBoxManage']
        cmd += ['showvminfo']
        cmd += [self.vm_name]
        proc = subprocess.Popen(cmd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        occurences = str(outs).count('running (since')
        if occurences:
            print('VM already running.')
        else:
            print('VM not running.')
        return bool(occurences)


class VMRunner(object):
    """
    Runs a project inside a existing Linux VM. The VM should run a relatively
    new version of either Debian Linux or Ubuntu. Except for the SSH server no
    additional software components are necessary.

    After installation of SSH server a new user "testrunner" has to be added:
        useradd testrunner

    For security reasons the PAM limits have to be changed in
    /etc/security/limits.conf:
        testrunner	hard	  nproc	      10
        testrunner	hard	  nofile      200
        testrunner  hard	  core		  500000
        testrunner  hard      data        500000
        testrunner  hard      fsize       500000
        testrunner  hard      stack       500000
        testrunner  hard      cpu         5
        testrunner  hard      as          500000
        testrunner  hard      nice        20
        testrunner	hard	  maxlogins	  1

    Finally the settings for connecting the VM (host, user, password, remote
    path) via SSH have to be adjusted.
    """
    def __init__(self, shutdown_vm_after=True):
        # timeout for execution in VM in seconds
        self.timeout = 10
        self.shutdown_vm_after = shutdown_vm_after
        # settings for connecting the VM via SSH
        self.vm_name = 'Debian_Testing'
        self.vm = VirtualBoxControl(self.vm_name)
        self.host = '192.168.10.130'
        self.username = 'testrunner'
        self.password = '1234'
        self.remote_path = '/home/testrunner/runner/'

    def rmtree(self, sftp, remotepath, level=0):
        """
        Deletes a whole directory including all sub-directories and all their
        files via SFTP. The function needs a connection to the SFTP server (uses
        Python library paramiko) and the path on the remote host.

        Source: http://stackoverflow.com/questions/3406734/how-to-delete-all-files-in-directory-on-remote-server-in-python
        """
        for f in sftp.listdir_attr(remotepath):
            rpath = posixpath.join(remotepath, f.filename)
            if stat.S_ISDIR(f.st_mode):
                self.rmtree(sftp, rpath, level=(level + 1))
            else:
                rpath = posixpath.join(remotepath, f.filename)
                print('[Remote] Removing %s%s' % ('    ' * level, rpath))
                sftp.remove(rpath)
        print('[Remote] Removing %s%s' % ('    ' * level, remotepath))
        sftp.rmdir(remotepath)

    def run(self, project):
        if not self.vm.start_VM():
            return (-1, '')
        if not os.path.exists(os.path.join(project.tempdir, project.target)):
            raise FileNotFoundError('Error: Executable file has not been created!')
        copy_to_vm = [os.path.join(project.tempdir, project.target)]
        copy_from_vm = ['CUnitAutomated-Results.xml']
        print('Connecting to remote machine...')
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.load_system_host_keys()
        client.connect(self.host, username=self.username, password=self.password, timeout=10)
        return_code = 0
        data = ''
        with client.open_sftp() as sftp:
            try:
                self.rmtree(sftp, self.remote_path)
            except FileNotFoundError:
                pass
            try:
                sftp.mkdir(self.remote_path)
            except OSError:
                pass
            for f in copy_to_vm:
                remote_file = os.path.join(self.remote_path, os.path.basename(f))
                sftp.put(f, remote_file)
                sftp.chmod(remote_file, 0o777)
                stdin, stdout, stderr = client.exec_command('cd {}; timeout {}s {}'.format(self.remote_path, self.timeout, remote_file))
                return_code = stdout.channel.recv_exit_status()
                print('[Remote] Error code: {}'.format(return_code))
                stdout_string = '[Remote] ' + ''.join(stdout)
                if stdout_string:
                    print('[Remote] STDOUT:')
                    print(stdout_string)
                stderr_string = '[Remote] ' + ''.join(stderr)
                if stderr_string:
                    print('[Remote] STDERR:')
                    print(stderr_string)
            for f in copy_from_vm:
                # get all result files
                remote_file = os.path.join(self.remote_path, os.path.basename(f))
                try:
                    with tempfile.TemporaryFile() as local_file:
                        sftp.getfo(remote_file, local_file)
                        local_file.seek(0)
                        data = local_file.read()
                except FileNotFoundError:
                    print('Remote file not found!')
            # delete all files in home directory
            self.rmtree(sftp, self.remote_path)
        client.close()
        if self.shutdown_vm_after:
            self.vm.stop_VM()
        return (return_code, data)


class DockerRunner(object):
    """
    Runs a project inside a Docker container.
    """
    def __init__(self):
        self.client = docker.Client(version='1.17')
        self.client.info()
        self.DOCKER_TIMEOUT = 2

    def run(self, project):
        """
        Runs a already compiled project inside a secure enviroment. This runner
        class uses a Docker container with restricted permissions to encapsulate
        the untrusted executable.

        :param project: project object containing all necessary file names etc.
        :returns: tuple containing the error code and the unit test results
        """
        img = 'autotest/' + project.target
        self.build_image(project, img)
        error_code, cont = self.start_container(img)
        if error_code:
            return (error_code, None)
        data = self.extract_file_from_container(cont, 'CUnitAutomated-Results.xml')
        self.stop_container(cont, img)
        return (0, data)

    def build_image(self, project, img):
        # check whether target file exists (has been compiled correctly)
        if not os.path.exists(os.path.join(project.tempdir, project.target)):
            raise FileNotFoundError('Error: Executable file has not been created!')
        dockerfile = """FROM scratch
                        COPY {target} /
                        CMD ["/{target}"]
                     """
        # build Dockerfile and Docker image
        # TODO: this should be possible in-memory
        with open(os.path.join(project.tempdir, 'Dockerfile'), 'w') as fd:
            fd.write(dockerfile.format(target=project.target))
        container_limits = {}
        container_limits['memory'] = 2**22      # memory limit for build
        container_limits['memswap'] = 2**22     # memory + swap, -1 to disable swap
        container_limits['cpushares'] = 10      # CPU shares (relative weight)
        container_limits['cpusetcpus'] = '0'    # CPUs in which to allow exection, e.g., '0-3', '0,1'
        #container_limits['cpu-quota'] = 10000   # 10% of CPU for this container
        build_out = self.client.build(path=project.tempdir, tag=img, rm=True, stream=False)
        [_ for _ in build_out]

    def start_container(self, img):
        # create container and start it (start unit tests, see Dockerfile)
        # TODO: check if image was created
        cont = self.client.create_container(image=img, network_disabled=True, mem_limit='4m', cpu_shares=10, memswap_limit=2**22)
        self.client.start(container=cont, network_mode='none', lxc_conf='lxc.cgroup.cpu.cfs_quota_us = 10000') # lxc.cgroup.memory.limit_in_bytes=4m')

        # Adds support for `--ulimit` parameter introduced in Docker 1.6
        # https://github.com/docker/docker/pull/9437
        # https://github.com/docker/docker/issues/6479
        # https://devlearnings.wordpress.com/2014/08/22/limiting-fork-bomb-in-docker/

        # Additional options for client.start():
        # security_opt='apparmor:PROFILE'
        # cap_add: Add Linux capabilities
        # cap_drop: Drop Linux capabilities
        # privileged=false: Give extended privileges to this container
        # devices: Allows you to run devices inside the container without the --privileged flag.
        # lxc-conf: Add custom lxc options
        #   lxc.cgroup.memory.limit_in_bytes = 512M
        #   lxc.cgroup.cpu.cfs_quota_us=50000  (see https://www.kernel.org/doc/Documentation/scheduler/sched-bwc.txt)
        # Source: https://docs.docker.com/reference/run/#runtime-privilege-linux-capabilities-and-lxc-configuration

        # output stdout from container
        #out = self.client.attach(container=cont, logs=True)
        #print(out.decode('utf-8'))

        # wait for container to exit or to reach the time out
        try:
            ret_val = self.client.wait(container=cont, timeout=self.DOCKER_TIMEOUT)
        except ReadTimeout:
            self.stop_container(cont, img)
            print('Timeout for container execution was reached')
            return (-1, None)
        # catch problem when unit test executable returns with error code
        if ret_val != 0:
            self.stop_container(cont, img)
            print('Error code returned: {}'.format(ret_val))
            return (ret_val, None)
        return (0, cont)

    def stop_container(self, cont, img):
        self.client.stop(container=cont)
        self.client.remove_container(container=cont)
        self.client.remove_image(image=img)

    def extract_file_from_container(self, cont, file_name):
        # extract unit test results from container (returned by dockerpy as tar stream)
        try:
            temp = self.client.copy(container=cont, resource='/{}'.format(file_name))
        except docker.errors.APIError as e:
            self.stop_container(cont, img)
            # TODO: is there a better way to check and handle this?!
            if 'Could not find the file' in e.explanation.decode('utf-8'):
                print('Could not extract cunit results. Maybe source does not contain test?!')
            return ReportPart('cunit', -1, [])
        buffer = BytesIO(temp.read())
        date = ''
        with tarfile.open(fileobj=buffer, mode='r') as tar:
            with tar.extractfile(file_name) as fd:
                data = fd.read()
        return data


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
    cb_unit_template = '<Unit filename="{filename}"><Option compilerVar="CC" /></Unit>'
    cb_unit_h_template = '<Unit filename="{filename}" />'

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
        self.target = base64.b64encode(self.project_name.encode('utf-8')).decode('utf-8').lower().replace('=', '')

        for f in self.file_list:
            if not os.path.isfile(f):
                raise FileNotFoundError('Source file {} not found!'.format(f))

        # TODO: test if libs are installed?!


    def create_cb_project(self, file_name='project.zip'):
        """
        Create a CodeBlocks project inside a ZIP file. A XML project file
        contains links to all source and header files and sets all necessary
        compiler options. Furthermore all include directories are added as
        search directories for the compiler.

        :param file_name: name for ZIP file containing CodeBlocks project
        :returns: name of ZIP file containing CodeBlocks project
        """
        unit_str = ''
        include_dirs = ''
        with ZipFile(file_name, 'w') as project_zip:
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
                for f in glob.glob(d + '/*.h'):
                    if f not in already_packed_files:
                        only_file_name = os.path.basename(f)
                        project_zip.write(f, only_file_name)
                        unit_str += self.cb_unit_h_template.format(filename=only_file_name)
                        already_packed_files.append(f)
            # include description file
            task_directory = os.path.dirname(os.path.dirname(self.file_list[0]))
            description_file_name = 'description.md'
            description_file = os.path.join(task_directory, description_file_name)
            unit_str += self.cb_unit_h_template.format(filename=description_file_name)
            project_zip.write(description_file, description_file_name)
            # include project file
            with tempfile.NamedTemporaryFile() as buffer:
                buffer.write(self.cb_project_template.format(title=self.project_name, units=unit_str,
                                                             include_dirs=include_dirs).encode('utf-8'))
                buffer.flush()
                project_zip.write(buffer.name, '{}.cbp'.format(self.project_name))
            # include layout file
            with tempfile.NamedTemporaryFile() as buffer:
                buffer.write(self.cb_layout_template.encode('utf-8'))
                buffer.flush()
                project_zip.write(buffer.name, '{}.layout'.format(self.project_name))
        return file_name


class Task(object):
    """
        Represents one Task. Contains all Informations, to create "packs" of
        files to check, compile or distribute.

        :ivar name          Name of the task.
        :ivar desc          Path to description file.
        :ivar scr_dir       Base dir for all files.
        :ivar files         General files included in all other "filesets"
        :ivar files_main    Files used for executing.
        :ivar files_test    Files used for testing.
        :ivar files_student Files to be added by the student or for the student in a cb project.
    """

    def __init__(self, path):
        self.path = path
        with open(os.path.join(path, 'config.json'), 'r') as fd:
            data = json.load(fd)
        self.name          = data['name']
        self.desc          = data['desc']
        self.libs          = data['libs']
        self.src_dir       = data['src_dir']
        self.files         = data['files']
        self.files_main    = data['files_main']
        self.files_test    = data['files_test']
        self.files_student = data['files_student']

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
    def __init__(self, backend='vm'):
        self.tempdir = tempfile.TemporaryDirectory()
        self.backend = backend
        self.check_env()

    def __del__(self):
        self.tempdir.cleanup()

    def check_env(self):
        # gcc
        try:
            subprocess.call(['gcc', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError('gcc not found!')
        # cppcheck
        try:
            subprocess.call(['cppcheck', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError('cppcheck not found!')
        # docker
        try:
            proc = subprocess.call(['docker', 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError('docker not found!')
        if proc != 0:
            raise FileNotFoundError('docker found but permission denied. Is user in group "docker"?')
        # cunit
        try:
            proc = subprocess.call(['ld', '-lcunit', '-o{tmpfile}'.format(tmpfile=os.path.join(self.tempdir.name, '__ld_check.out'))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise FileNotFoundError('ld not found!')
        if proc != 0:
            raise FileNotFoundError('cunit not found!')
        # docker-py
        version_info = tuple([int(d) for d in docker.version.split('-')[0].split('.')])
        if version_info[0] < 1 or version_info[0] == 1 and version_info[1] < 2:
            raise FileNotFoundError('docker-py version to old!')

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
            print('Error: Could not run compiler because CppCheck returned error code.')
        if _r.returncode == 0:
            checker = CunitChecker(backend=self.backend)
            _r = checker.run(project)
            self.print_unit_test_results(checker.parser.list_of_tests)
            r.add_part(_r)
        else:
            print('Error: Could not run unit tests because Compiler returned error code.')

        project.tempdir = None
        return r

    def print_unit_test_results(self, testresults):
        """
        Prints test results to console if tests have been successfully executed.

        :param testresults: dictionary containing the results for all test
                            suites and their unit tests
        """
        if testresults:
            print('=====')
            for suite in sorted(testresults):
                print('Suite: {}'.format(suite))
                for test in sorted(testresults[suite]):
                    print('{:30s} - {}'.format(test, 'success' if testresults[suite][test] else 'failure'))
            print('=====')


def parse_args():
    parser = argparse.ArgumentParser(description='libConCoct - Builds simple C programs and runs unit tests.',
                                     epilog='Copyright 2015 by Martin and Christian Wichmann')
    parser.add_argument('-u', '--unittest', action='store_true', help='run unit tests on solution')
    parser.add_argument('-p', '--project', action='store_true', help='create CodeBlocks project for task')
    parser.add_argument('--project-file-name', help='name of the ZIP file containing the CodeBlocks project')
    parser.add_argument('-t', '--task', required=True, help='task to run unit tests or create project file for')
    parser.add_argument('-s', '--solution', type=argparse.FileType('r'), help='solution to test against unit tests')
    parser.add_argument('-b', '--backend', choices=['vm', 'docker'], default='vm', help='backend used for running unit tests in secure environment')
    cmd_options = parser.parse_args()
    return cmd_options


def find_all_tasks(tasks_path='tasks'):
    tasks = []
    for d in os.listdir(tasks_path):
        try:
            t = Task(os.path.join(tasks_path, d))
            if t is not None:
                tasks.append(t)
        except FileNotFoundError:
            pass
    return tasks


def test_examples():
    try:
        w = ConCoCt()
    except FileNotFoundError as e:
        sys.exit(e)
    t = Task(os.path.join('tasks', 'greaterZero'))
    s1 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/solutions/greaterZero/user1/solution.c', ))
    s2 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/solutions/greaterZero/user2/solution.c', ))
    s3 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/kill_container.c', ))
    # create test project and unit test it
    p = t.get_test_project(s2)
    r = w.check_project(p)
    print(r)


def build_project_examples():
    try:
        w = ConCoCt()
    except FileNotFoundError as e:
        sys.exit(e)
    t = Task(os.path.join('tasks', 'greaterZero'))
    s1 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/solutions/greaterZero/user1/solution.c', ))
    s2 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/solutions/greaterZero/user2/solution.c', ))
    s3 = Solution(t, ('/home/christian/Programmierung/python/UpLoad2/libconcoct/kill_container.c', ))
    # create CodeBlocks project
    p = t.get_main_project(None)
    p.create_cb_project()


def run_libconcoct():
    options = parse_args()
    if not options.unittest and not options.project:
        print('No action ("unittest" or "project") chosen!')
        return
    t = Task(options.task)
    if options.solution:
        s = Solution(t, (options.solution.name, ))
    else:
        s = None
    if options.unittest:
        print('Using backend: {}'.format(options.backend))
        try:
            w = ConCoCt(backend=options.backend)
        except FileNotFoundError as e:
            sys.exit(e)
        p = t.get_test_project(s)
        r = w.check_project(p)
        print(r)
    elif options.project:
        p = t.get_main_project(s)
        if 'project-file-name' in options:
            p.create_cb_project(file_name=options['project-file-name'])
        else:
            p.create_cb_project()


if __name__ == '__main__':
    run_libconcoct()
    #test_examples()
    #build_project_examples()
