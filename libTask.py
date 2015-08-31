#!/usr/bin/python
"""
libTask.py - library of routines for handling task...maybe come a module 
"""

# Stock modules
import sys
import os
import re
import logging
import traceback
import datetime
import collections
import operator
import itertools
import json
import jsonschema
import pprint

# Local modules
from utils import *
import error_codes

LOG = logging.getLogger(__name__)

taskSchema={
  "$schema": "http://json-schema.org/draft-04/schema#",
  "description": "task schema",
  "type": "array",
  "items": {
     "type": "object"
  }
}

def read_tasks_json_file(jsonFile):
    '''Read Task list JSON file'''
    try:
        LOG.info("Processing task list JSON file: {}".format(jsonFile))
        tasks = json.load(open(jsonFile, 'r'), object_pairs_hook=collections.OrderedDict)

        validator = jsonschema.Draft4Validator(taskSchema)
        errs = sorted(validator.iter_errors(tasks), key=lambda e: e.path)

        if errs:
            msg=""
            for err in errs:
                msg+=err.message
            error(LOG,msg,error_codes.EX_IOERR)

    except:
        LOG.info("Unable to open/process: {} task list json file".format(jsonFile))
        # CS -- What if there is no completed file? The return fails.
        tasks = []
    return(tasks)

def write_tasks_json_file(jsonFile,tasks):
    '''Write New Processed Image Files'''

    try:
        taskFH = open(jsonFile,"w")
        taskFH.write(json.dumps(tasks,indent=2,skipkeys=True))
        taskFH.close()
    except:
        msg="Unable to open/write: {} task list json file".format(jsonFile)
        error(LOG,msg,error_codes.EX_IOERR)

    return()

def sort_tasks(tasks,keyOption,reverseOption):

    try:
        sortedTasks = sorted(tasks, key=operator.itemgetter(keyOption), reverse=reverseOption)
    except:
        msg="Unable to sort task list"
        error(LOG,msg,error_codes.EX_IOERR)

    return(sortedTasks)

def compare_tasks(tasks1,tasks2):

    try:
        diffList = list(itertools.ifilterfalse(lambda x: x in tasks1, tasks2)) \
                 + list(itertools.ifilterfalse(lambda x: x in tasks2, tasks1))
    except:
        msg="Unable to compare task lists"
        error(LOG,msg,error_codes.EX_IOERR)

    return(diffList)

def new_tasks(tasks,updatedTasks):

    try:
        newTasks = list(itertools.ifilterfalse(lambda x: x in tasks, updatedTasks))

    except:
        msg="Unable to get new task lists"
        error(LOG,msg,error_codes.EX_IOERR)

    return(newTasks)

def prepend_tasks(tasks,prependTasks):

    try:
        tasks[:0] = prependTasks
    except:
        msg="Unable to prepend task lists"
        error(LOG,msg,error_codes.EX_IOERR)

    return(True)

def print_tasks(tasks):

    # pp = pprint.PrettyPrinter(indent=4,depth=20)
    # pp.pprint(tasks)
 
    print json.dumps(tasks,indent=4)

    return()

def print_tasks_keys_values(tasks,key):

    values=[]
    for task in tasks:
        values.append(task[key])
 
    return(values)
