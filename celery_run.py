#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import celery_tasks
import time
import os
from libConCoCt import Task, Solution

task_directory = os.path.join('tasks', 'greaterZero')
solution_file = (os.path.join('solutions', 'greaterZero', 'user2', 'solution.c'), )
building = celery_tasks.build_and_check_task_with_solution.delay(task_directory,
                                                                 solution_file)

while not building.ready():
    print('Waiting...')
    time.sleep(0.2)

print(building.get())
