# libConCoct

## Description
Automatic compile and test of simple c programs.


## Usage
libConCoct can be used on the command line or through a Ceelry worker.

### CLI 
With the command line interface you can compile and unit test a solution for a
given task and create a ZIP file containing a CodeBlocks project. You can test
this with one of the example tasks:

    ./libConCoCt.py -u -t tasks/leapyear/ -s solutions/leapyear/user1/solution.c -b vm
    
    ./libConCoCt.py -u -t tasks/fizzbuzz/ -s solutions/fizzbuzz/user1/solution.c -b docker


### Celery
Celery is a asynchronous task queue that takes tasks via the standard Advanced
Message Queuing Protocol (AMQP). For Celery to take tasks for compiling and
testing C programs first a worker instance has to be started in the background:

    celery worker -A celery_tasks &

After that you can put tasks in the queue using different programming languages
and enviroments. An example how to use it in Python can be found in the file
celery_run.py:

    ./celery_run.py


## License
libConCoCt is released under the MIT License.


## Requirements
libConCoct runs with at least Python 3.3.


## Problems
Please go to http://github.com/m-wichmann/libConCoct to submit bug reports,
request new features, etc.


## Third party software
libConCoct includes parts of or links with the following software packages and
programs, so give the developers lots of thanks sometime!

* Paramiko - A Python implementation of the SSHv2 protocol. Licensed under the
  GNU LGPL license.
* Celery and RabbitMQ - An open source asynchronous task queue (Celery) based on
  distributed message passing (RabbitMQ). Licensed under the BSD License and the
  Mozilla Public License respectively.
* Docker - An open platform for building, shipping and running distributed
  applications. Licensed under the Apache 2.0 license.
* Oracle VirtualBox - A virtualization solution for x86 and AMD64/Intel64.
  Available under the terms of the GNU General Public License (GPL) version 2.
* Some cliparts from opencliparts.org:
   - https://openclipart.org/detail/212046/emblem-gear
