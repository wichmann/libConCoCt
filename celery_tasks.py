
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


from celery import Celery
from libConCoCt import Task, Solution, ConCoCt


# CELERY SETTINGS
BROKER_URL = 'amqp://'
BACKEND = 'amqp'
CELERY_ACCEPT_CONTENT = ['pickle', 'json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'


app = Celery('tasks', backend=BACKEND, broker=BROKER_URL)


# TODO Remove name parameter here and cleanup imports in Celery worker (this
#      file) and 'entry' controller.
@app.task(name='applications.ConCoct.modules.celery_tasks.build_and_check_task_with_solution')
def build_and_check_task_with_solution(tasks_store_path, solution_path):
    try:
        t = Task(tasks_store_path)
    except FileNotFoundError as e:
        sys.exit(e)
    s = Solution(t) #, 'path to solution'
    try:
        w = ConCoCt()
    except FileNotFoundError as e:
        sys.exit(e)
    p = t.get_test_project(None) # s
    r = w.check_project(p)
    return r.to_json()
