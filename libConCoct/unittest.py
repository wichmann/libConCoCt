
"""
Contains all a class to run unit tests in a secure environment and parse the
results into an Report.

Currently there are two environments in which the unit tests can be run:
running inside a Docker container or copy executable via SSH to a virtual
machine and run unit tests on the VM.

Authors: Martin Wichmann, Christian Wichmann
"""

from __future__ import print_function

import os
import tempfile
import time
import subprocess
from collections import defaultdict
import xml.etree.ElementTree
from io import BytesIO
import tarfile
from requests.exceptions import ReadTimeout
from functools import wraps

# imports for VM  and docker runner
from paramiko.client import SSHClient
from paramiko import AutoAddPolicy
import posixpath
import stat
import docker

from .report import Message
from .report import ReportPart


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
                    assert 0
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
            cmd = ['VBoxManage']
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
        cmd = ['VBoxManage']
        cmd += ['controlvm']
        cmd += [self.vm_name]
        cmd += ['acpipowerbutton']
        return_code = subprocess.call(cmd)
        print('Shutdown: {}'.format(return_code))
        return bool(return_code)

    def check_VM(self):
        cmd = ['VBoxManage']
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


def with_started_vm(shutdown_vm_after=False, vm_name='', error_value=None):
    def wrapper(func):
        @wraps(func)
        def wrapped_function(*args, **kwargs):
            vm = VirtualBoxControl(vm_name)
            if not vm.start_VM():
                return error_value
            results = func(*args, **kwargs)
            if shutdown_vm_after:
                vm.stop_VM()
            return results
        return wrapped_function
    return wrapper


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
        self.host = '192.168.56.101'
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

    @with_started_vm(vm_name='Testrunner', shutdown_vm_after=False, error_value=(-1, ''))
    def run(self, project):
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
        return return_code, data


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
        Runs a already compiled project inside a secure environment. This runner
        class uses a Docker container with restricted permissions to encapsulate
        the untrusted executable.

        :param project: project object containing all necessary file names etc.
        :returns: tuple containing the error code and the unit test results
        """
        img = 'autotest/' + project.target
        self.build_image(project, img)
        error_code, cont = self.start_container(img)
        if error_code:
            return error_code, None
        data = self.extract_file_from_container(cont, img, 'CUnitAutomated-Results.xml')
        self.stop_container(cont, img)
        return 0, data

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
        # container_limits['cpu-quota'] = 10000   # 10% of CPU for this container
        build_out = self.client.build(path=project.tempdir, tag=img, rm=True, stream=False)
        [_ for _ in build_out]

    def start_container(self, img):
        """
        Creates a docker container based on a given image and starts it (start
        unit tests, see Dockerfile). This function returns an error code and
        the container object. If the container could be created and ran
        successfully it will return a 0 as error code, otherwise a -1.

        :param img: image for which to create a Docker container
        :return: error code and container object
        """
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
        # out = self.client.attach(container=cont, logs=True)
        # print(out.decode('utf-8'))

        # wait for container to exit or to reach the time out
        try:
            ret_val = self.client.wait(container=cont, timeout=self.DOCKER_TIMEOUT)
        except ReadTimeout:
            self.stop_container(cont, img)
            print('Timeout for container execution was reached')
            return -1, None
        # catch problem when unit test executable returns with error code
        if ret_val != 0:
            self.stop_container(cont, img)
            print('Error code returned: {}'.format(ret_val))
            return ret_val, None
        return 0, cont

    def stop_container(self, cont, img):
        self.client.stop(container=cont)
        self.client.remove_container(container=cont)
        self.client.remove_image(image=img)

    def extract_file_from_container(self, cont, img, file_name):
        # extract unit test results from container (returned by dockerpy as tar stream)
        try:
            temp = self.client.copy(container=cont, resource='/{}'.format(file_name))
        except docker.errors.APIError as e:
            self.stop_container(cont, img)
            # TODO: is there a better way to check and handle this?!
            if 'Could not find the file' in e.explanation.decode('utf-8'):
                print('Could not extract cunit results. Maybe source does not contain test?!')
            return ReportPart('cunit', -1, [])
        content = BytesIO(temp.read())
        date = ''
        with tarfile.open(fileobj=content, mode='r') as tar:
            with tar.extractfile(file_name) as fd:
                data = fd.read()
        return data
