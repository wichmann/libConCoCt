
import celery_tasks
import time
import os
from libConCoCt import Task, Solution


building = celery_tasks.build_and_check_task_with_solution.delay(os.path.join('..', 'private', 'tasks', 'task2'), '')

while not building.ready():
    print('Waiting...')
    time.sleep(1)

print(building.get())
