#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""
Executes an example task on a Celery worker in the background. Before this file
is executed, the worker instance has to be started. In this example a single
solution for a given task is compiled, executed and tested. While building and
testing runs in the background, this files process sleeps and waits for the
worker to finish.

Start this example task:
    ./celery_run.py

Authors: Christian Wichmann
"""

import celery_tasks
import time
import os


def build_example():
    # Available tasks: leapyear greaterZero, fizzbuzz
    task_directory = os.path.join('tasks', 'fizzbuzz')
    solution_file = (os.path.join('solutions', 'fizzbuzz', 'user1', 'solution.c'), )
    building = celery_tasks.build_and_check_task_with_solution.delay(task_directory,
                                                                     solution_file)
    while not building.ready():
        print('Waiting...')
        time.sleep(0.2)
    print(building.get())


if __name__ == '__main__':
    build_example()
