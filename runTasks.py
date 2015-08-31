#!/usr/bin/python
"""
runTasks.py - creates and runs tasks from a json configuration file, which specifies the plugin task, work, and purge methods
              for generating, executing, and removing tasks. Completed tasks are written to a task list json file for future runs
              and in the event of a system failure.
"""

# Stock modules
import sys
import os
import re
import psutil
import datetime
import optparse  # deprecated
import operator
import collections
import copy
import json
import jsonschema
import importlib
import logging
import traceback

# Log
from setup_logging import *

# Local modules
import error_codes
import fileAction
import dirRE
from utils import *
from libTask import *

# setup logging
logging_setup = "runTasks"
setup_logging(logging_setup)
LOG = logging.getLogger('runTasks')  # create the logger for this file


def error(LOG, msg="Unexpected Error:", code=1):
    '''Error Handing Routines'''
    LOG.exception(msg)
    sys.exit(code)

# Variables
runDTG = datetime.datetime.utcnow()
ISODTSFormat = "%Y%m%dT%H%M%S"
schema_task = json.load(open('schema_task.json', 'r'), object_pairs_hook=collections.OrderedDict)

# Determine if process is running, or in zombie state
cpid = os.getpid()
commandRE = "^{}$".format(" +".join([sys.executable] + sys.argv))
# LOG.info("Command RE: {}".format(commandRE))
procs = getProcesses(commandRE)
if cpid in procs:
    del procs[cpid]
if len(procs) > 0:
    for pid in procs:
        if procs[pid].status() != psutil.STATUS_ZOMBIE:
            LOG.info("Process {} ({}) is running, exiting".format(__file__, pid))
            # LOG.info("Process Command Line: {}".format(procs[pid].cmdline()))
            sys.exit(0)
        else:
            LOG.info("Process {} ({}) is in zombie state, terminating".format(__file__, pid))
            procs[pid].kill()

# Read Command Line Arguments
options = optparse.OptionParser()
options.add_option("-c", "--config", dest="config", help="Configuration File")

try:
    (opts, args) = options.parse_args()
    config_filename = opts.config

except:
    msg = 'Syntax: python runTasks.py -c <config.json>'
    error(LOG, msg, error_codes.EX_USAGE)

# Read and Validate Configuration File
try:
    LOG.info("Processing JSON config file: {}".format(config_filename))
    config = json.load(open(config_filename), object_pairs_hook=collections.OrderedDict)

    validator = jsonschema.Draft4Validator(schema_task)
    errs = sorted(validator.iter_errors(config), key=lambda e: e.path)

    if errs:
        msg = ""
        for err in errs:
            msg += err.message
        error(LOG, msg, error_codes.EX_IOERR)

except:
    msg = "Error in JSON config file: {}".format(config_filename)
    error(LOG, msg, error_codes.EX_IOERR)

# Load library module
try:
    module = importlib.import_module(config['plugin']['module'])
    purgeMethod = config['plugin']['purge']
    tasksMethod = config['plugin']['tasks']
    workMethod = config['plugin']['work']
except:
    msg = "Unable to load module: {}".format(config['plugin']['module'])
    error(LOG, msg, error_codes.EX_IOERR)

# Determine run, backward search DTG and iteration delta
meta = config['meta']
meta['runDTG'] = runDTG
meta['bkwdDTG'] = meta['runDTG']-datetime.timedelta(seconds=meta['bkwdDelta'])
LOG.info("Run datetime: {}".format(meta['runDTG'].strftime(ISODTSFormat)))
LOG.info("Backward search datetime: {}".format(meta['bkwdDTG'].strftime(ISODTSFormat)))

# Add config replace section, add DTG strings
config['replace'] = {}
config['replace'].update(DTGrangeToStrings(meta['bkwdDTG'], meta['runDTG'], meta['DTGfrmts']))
# print json.dumps(config['replace'])

# Copy master config to workConfig
workConfig = copy.deepcopy(config)
primeTasksKey = workConfig['primeTasksKey']

# Read task list json file
LOG.info("Reading processed tasks JSON file: {}".format(config['completeTaskFile']))
readTasks = read_tasks_json_file(config['completeTaskFile'])

# Purge unneeded tasks using plug-in purge method
try:
    args = [workConfig, readTasks]
    completeTasks = getattr(module, purgeMethod)(*args)
    del readTasks[:]
except:
    msg = "Problem in module: {} purge method: {}".format(module, purgeMethod)
    error(LOG, msg, error_codes.EX_IOERR)

# Create task list from plug-in tasks method
try:
    LOG.info("Creating new tasks list")
    args = [workConfig]
    createdTasks = getattr(module, tasksMethod)(*args)
except:
    msg = "Problem in module: {} tasks method: {}".format(module, tasksMethod)
    error(LOG, msg, error_codes.EX_IOERR)

# Compare created and completed tasks lists, put difference into task list
tasks = new_tasks(completeTasks, createdTasks)
del createdTasks[:]

# Iterate through tasks, newest to oldest, insert into completeTask list
# and update complete task list file, after each complete task (incase of system failure)

executedTasks = []
incompleteTasks = []
LOG.info("Running Tasks...")
while(tasks):

    LOG.info("Tasks in queue: {}".format(len(tasks)))
    LOG.info("{}".format(print_tasks_keys_values(tasks, primeTasksKey)))

    # Get latest task
    task = tasks.pop(0)

    # Execute task
    try:
        args = [workConfig, task]
        status = getattr(module, workMethod)(*args)
        if status:
            LOG.info("Task: {} completed".format(print_tasks_keys_values([task], primeTasksKey)))
            executedTasks.append(task)
        else:
            LOG.warning("Problem completing task: {}, dequeing task and continuing to next task".format(print_tasks_keys_values([task], primeTasksKey)))
            incompleteTasks.append(task)

    except:
        LOG.warning("Unable to complete task, dequeing task and continuing to next task")
        traceback.print_exc(file=sys.stdout)
        incompleteTasks.append(task)

    # Determine if any new tasks are available
    try:
        LOG.info("Searching for new tasks")
        args = [workConfig]
        createdTasks = getattr(module, tasksMethod)(*args)
    except:
        msg = "Problem in module: {} tasks routine: {}".format(module, tasksMethod)
        error(LOG, msg, error_codes.EX_IOERR)

    # Compare complete, created, executed and current tasks lists, prepend new tasks to task list
    workTasks = new_tasks(completeTasks, createdTasks)
    del createdTasks[:]
    workTasks = new_tasks(executedTasks, workTasks)
    workTasks = new_tasks(incompleteTasks, workTasks)
    workTasks = new_tasks(tasks, workTasks)
    LOG.info("Adding tasks: {}".format(print_tasks_keys_values(workTasks, primeTasksKey)))
    prepend_tasks(tasks, workTasks)
    del workTasks[:]

    # Update completed tasks list json file
    LOG.info("Updating completed tasks list JSON file: {}".format(config['completeTaskFile']))
    writeTasks = executedTasks + completeTasks
    writeTasks = sort_tasks(writeTasks, primeTasksKey, workConfig['sortReverseOption'])
    write_tasks_json_file(config['completeTaskFile'], writeTasks)
    del writeTasks[:]


LOG.info("Tasks Executed:")
LOG.info("{}".format(print_tasks_keys_values(executedTasks, primeTasksKey)))
LOG.info("Completed")
