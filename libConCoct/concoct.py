
"""
Contains the main data classes with all necessary information to build a
project including a provided solution and run it against unit tests.

Furthermore a CodeBlocks ([1]) project can be created as ZIP file containing
all files to run the project on ones own system.

[1] http://www.codeblocks.org/

Authors: Martin Wichmann, Christian Wichmann
"""

import tempfile
import subprocess
import base64
import glob
import json
import os
from zipfile import ZipFile
import docker

from .report import Report
from .unittest import CunitChecker
from .checker import CppCheck
from .compiler import CompilerGcc


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
                # include_dirs += """<Add directory="{dir}" />""".format(dir=d)
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
        Represents one Task and contains all its information, to create "packs" of
        files to check, compile or distribute.

        :ivar name:          Name of the task.
        :ivar desc:          Path to description file.
        :ivar scr_dir:       Base dir for all files.
        :ivar files:         General files included in all other "filesets"
        :ivar files_main:    Files used for executing.
        :ivar files_test:    Files used for testing.
        :ivar files_student: Files to be added by the student or for the student in a cb project.
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
