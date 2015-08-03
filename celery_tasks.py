# -*- encoding: utf-8 -*-

"""
Implements a celery worker function to build a project and unit test it.

In production we can use supervisord to start Celery workers and make sure they
are restarted in case of a system reboot or crash.

-> http://michal.karzynski.pl/blog/2014/05/18/setting-up-an-asynchronous-task-queue-for-django-using-celery-redis/
-> https://github.com/celery/celery/blob/3.1/extra/supervisord/celeryd.conf

Start this worker in background with:
    celery worker -A celery_tasks &

Stop all workers with:
    ps auxww | grep 'celery worker' | awk '{print $2}' | xargs kill -9
"""


import sys
from celery import Celery
from libConCoCt import Task, Solution, ConCoCt


# CELERY SETTINGS
BROKER_URL = 'amqp://'
BACKEND = 'amqp'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'


app = Celery('tasks', backend=BACKEND, broker=BROKER_URL)


# TODO Remove name parameter here and cleanup imports in Celery worker (this
#      file) and 'entry' controller.
@app.task(name='applications.ConCoct.modules.celery_tasks.build_and_check_task_with_solution')
def build_and_check_task_with_solution(task_store_path, solution_file_list):
    """
    Builds a given task with a given solution by a user. The task defines unit
    tests and helper function that are used to determine, if the task has been
    sucessfully solved.

    :param task_store_path: path to the task directory containing the task
                            description, configuration file and all source
                            files necessary to build and test the task
    :param solution_file_list: list of files submitted as possible solution for
                               the given task
    """
    try:
        t = Task(task_store_path)
    except FileNotFoundError as e:
        sys.exit(e)
    s = Solution(t, solution_file_list)
    try:
        w = ConCoCt()
    except FileNotFoundError as e:
        sys.exit(e)
    p = t.get_test_project(s)
    r = w.check_project(p)
    return r.to_json()
