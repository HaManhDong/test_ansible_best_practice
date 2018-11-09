#!/usr/bin/env python

# Copyright 2017 Duong, Ha-Quang <duonghq@vn.fujitsu.com>
# Copyright 2018 Dong, Ha-Manh <donghm@vn.fujitsu.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

DOCUMENTATION = '''
---
plugin: not_run_all
short_description: Plugin for Ansible strategy
description:
  - Allowed task with 'not_run_all' variable can be run same as serial
    function. The'serial_ratio' variable affects how many hosts will
    run in a batch.
options:
  not_run_all:
    description:
      - Mark the task should run in 'not_run_all strategy'
    required: True
    type: any type
  serial_ratio:
    description:
      - Specific how many percent hosts will run in a batch
    default: 0.5
    required: False
    type: float
author: duonghq, donghm
'''

EXAMPLES = '''
Restart glance_api in a batch with 30% of hosts:

- hosts: glance_api
  strategy: not_run_all
  tasks:
    - name: Restart glance-api container
      vars:
        not_run_all: true
        serial_ratio: 0.3
      become: true
      kolla_docker:
        ...
      when:
        ...
'''

from ansible.template import Templar
from ansible.plugins.strategy.linear import (StrategyModule
                                             as LinearStrategyModule)
from ansible.module_utils import basic
from six import with_metaclass

import logging
logger = logging.getLogger('myapp')
hdlr = logging.FileHandler('/var/tmp/myapp.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.WARNING)
logger.error(' ')
logger.error(' ')
logger.error('=========================================')

class StrategyModule(with_metaclass(type, LinearStrategyModule)):
    def __init__(self, tqm):
        super(StrategyModule, self).__init__(tqm)
        self._pending_host = []
        self._original_length = 0

    def _get_next_task_lockstep(self, hosts, iterator):
        rvals = []

        if len(self._pending_host) > 0:
            rvals = self._pending_host[:self._batch_size]
            self._pending_host = self._pending_host[self._batch_size:]
        else:
            host_tasks = super(StrategyModule, self) \
                ._get_next_task_lockstep(hosts, iterator)
            self._original_length = len(host_tasks)
            logger.error('======== NEXT host_tasks ============')
            logger.error('host_tasks: %s', host_tasks)
            if len(host_tasks) > 0:
                host, cur_task = host_tasks[0]
                rvals = host_tasks
                if cur_task:
                    not_run_all = cur_task.get_vars().get('not_run_all')
                    task_vars = self._variable_manager.get_vars(play=iterator._play, host=host, task=cur_task)
                    templar = Templar(loader=self._loader, variables=task_vars)
                    if str(templar.template(not_run_all)).lower() == 'true':
                        # logger.error('templar: %s', str(templar.template(not_run_all)))
                        # logger.error('not_run_all not run all: %s', not_run_all)
                        serial_ratio = templar.template(task_vars.get('serial_ratio'))
                        if serial_ratio is None:
                            serial_ratio = 0.5
                        else:
                            serial_ratio = float(serial_ratio)
                        self._batch_size = \
                            int(self._original_length * serial_ratio)

                        # ensure the task will run on at lead one host
                        # in case the serial_ratio is too small
                        if self._batch_size == 0:
                            self._batch_size = 1

                        self._pending_host = host_tasks[(self._batch_size):]
                        rvals = host_tasks[:(self._batch_size)]

        return rvals

    def run_handlers(self, iterator, play_context):
        # Runs handlers on those hosts that have been notified.
        # If the handler tasks have the 'not_run_all' variable, there tasks
        # will be scheduled to run in a batch (serial_ratio) of those hosts.

        result = self._tqm.RUN_OK

        for handler_block in iterator._play.handlers:
            # FIXME (from Ansible note): handlers need to support the
            # rescue/always portions of blocks too, but this may take
            # some work in the iterator and gets tricky when
            # we consider the ability of meta tasks to flush handlers
            for handler in handler_block.block:
                if handler._uuid in self._notified_handlers and \
                        len(self._notified_handlers[handler._uuid]):
                    not_run_all = handler.get_vars().get('not_run_all')
                    task_vars = self._variable_manager.get_vars(play=iterator._play, task=handler)
                    templar = Templar(loader=self._loader, variables=task_vars)
                    if str(templar.template(not_run_all)).lower() == 'true':
                        serial_ratio = templar.template(handler.get_vars().get('serial_ratio'))
                        if serial_ratio is None:
                            serial_ratio = 0.5
                        else:
                            serial_ratio = float(serial_ratio)
                        batch = int(len(self._notified_handlers[handler._uuid])
                                    * serial_ratio)

                        # ensure the task will run on at lead one host
                        # in case the serial_ratio is too small
                        if batch == 0:
                            batch = 1
                        notified_hosts = self._notified_handlers[handler._uuid]
                        while len(notified_hosts):
                            result = \
                                self._do_handler_run(
                                    handler,
                                    handler.get_name(),
                                    iterator=iterator,
                                    play_context=play_context,
                                    notified_hosts=notified_hosts[:batch])
                            notified_hosts = notified_hosts[batch:]
                            if not result:
                                break
                    else:
                        result = \
                            self._do_handler_run(handler, handler.get_name(),
                                                 iterator=iterator,
                                                 play_context=play_context)
                        if not result:
                            break
        return result
