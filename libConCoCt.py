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
import os
import argparse

from libConCoct.concoct import Task
from libConCoct.concoct import Solution
from libConCoct.concoct import ConCoCt


__version__ = '0.1.0'


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
