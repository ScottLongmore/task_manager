#!/usr/bin/python
"""
  plgnGOES16_CONUS_Geocolor_BF.py - plug-in methods: TASKS, WORK, PURGE
"""

# Stock modules
import sys
import os
import re
import copy
import logging
import traceback
import datetime
import collections
import operator
import subprocess
import shutil

# Local modules
import error_codes
import fileAction
import dirRE

LOG = logging.getLogger(__name__)  # create the logger for this file

# Parameters
DTSFormat = "%Y%m%d%H%M%S"
ISODTSFormat = "%Y%m%dT%H%M%S"

def PURGE(config, tasks):
    """
    Removes tasks with DTS older than backward search datetime

    Parameters
    ----------
    config : dict
    tasks : dict

    Returns
    currentTasks : dict
        dictionary of current tasks to run
    """
    currentTasks = []
    for task in tasks:
        taskDTG = datetime.datetime.strptime(task['DTS'], ISODTSFormat)
        if taskDTG > config['meta']['bkwdDTG']:
            currentTasks.append(task)

    return(currentTasks)


def TASKS(config):
    """
    Generates list of tasks to run

    Parameters
    ----------
    config : dict
    """
    meta = config['meta']
    inputs = config['inputs']['GOES16_CONUS_Geocolor']

    LOG.info("Starting {} TASKS creation".format(config['name']))

    # Find task files
    FA = fileAction.fileAction(config)
    filepaths = FA.findInputFiles(['GOES16_CONUS_Geocolor'])['GOES16_CONUS_Geocolor']
    fileDTGs = {}
    for filepath in filepaths:

        filename=os.path.basename(filepath)
        m = re.match(inputs['re'], filename)
        fields = m.groupdict()
        DTS = fields['DTS']
        DTG = datetime.datetime.strptime(DTS, DTSFormat)
        if DTG not in fileDTGs:
            fileDTGs[DTG] = collections.OrderedDict()
        fileDTGs[DTG] = filepath

    DTGs = fileDTGs.keys()
    DTGs.sort()

    tasks = []
    for idx in xrange(0,len(DTGs)-1): 

        sDTG=DTGs[idx]
        eDTG=DTGs[idx+1]
        delta=eDTG-sDTG

        if inputs['period']-inputs['epsilon'] <= delta.total_seconds() <= inputs['period']+inputs['epsilon']:
           task={
                 'DTS':DTG.strftime(ISODTSFormat),
		 'sDTS':sDTG.strftime(ISODTSFormat),
		 'eDTS':eDTG.strftime(ISODTSFormat),
                 'sFile':fileDTGs[sDTG],
                 'eFile':fileDTGs[eDTG]
                }
           tasks.append(task)
           LOG.info("For task: {}".format(DTS))
	   LOG.info("Adding start File: {}".format(task['sFile'])) 
           LOG.info("Adding end File: {}".format(task['eFile']))
        else:
           LOG.warning("Delta: {} out of range".format(delta.total_seconds()))
           LOG.warning("For file: {}".format(fileDTGs[sDTG]))
           LOG.warning("And file: {}".format(fileDTGs[eDTG]))

    # Remove any older tasks than backward search datetime
    tasks = PURGE(config, tasks)

    LOG.info("Completed {} TASKS creation".format(config['name']))
    return(tasks)


def WORK(config, task):
    """
    The work to be done for each task

    Parameters
    ----------
    config : dict
    task : dict

    Returns
    -------
    status : Boolean
    """
    meta = config['meta']
    inputs = config['inputs']['GOES16_CONUS_Geocolor']
    plugin=config['plugin']

    taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)
  
    LOG.info("Starting {} WORK for task: {}".format(config['name'],task['DTS']))

    status = True 
    return(status)

    # Create work directory 
    workDir=os.path.join(str(config['workDirRoot']),task['DTS'])
    tdfDir=str(config['workDirRoot'])
    if not os.path.exists(workDir):
       LOG.info('Creating working directory: {}'.format(workDir))
       try:
           os.makedirs(workDir)
       except:
           LOG.warning("Unable to create work dir {}".format(workDir))
           status=False
           return(status)

    # CD to work directory
    try:
        LOG.info('Changing to working directory: {}'.format(workDir))
        os.chdir(workDir)
    except:
        LOG.warning("Unable to change to work dir: {}".format(workDir))
        status=False
        return(status)

    # Link task image files to working directory

    # Executing createBFImages
    try:
        commandList=[plugin['pythonExe'],plugin['createBFImagesExe']]
        commandArgs=['-c',plugin['createBFImagesCfg'],'-t',plugin['timeStep'],'-f',inputs['fileFormat'],'-s',workDir,'-o'
        commandID=taskDTG.strftime(DTSFormat)
        if not execute(commandList,commandArgs,commandID,workDir):
            LOG.warning("Execute failed for {}".format(plugin['DEBRAScp']))
            status=False
            return(status)


    except:

def execute(commandList,commandArgs,commandID,workDir):

    command=commandList[-1]

    commandLine=[]
    commandLine.extend(commandList)
    commandLine.extend(commandArgs)

    status=True
    try:
        base, ext =os.path.splitext(os.path.basename(command))
        outFile=os.path.join(workDir,"{}_{}.stdout".format(base,commandID))
        errFile=os.path.join(workDir,"{}_{}.stderr".format(base,commandID))
        outfh=open(outFile,'w')
        errfh=open(errFile,'w')
        LOG.info("STDOUT File: {}".format(outFile))
        LOG.info("STDERR File: {}".format(errFile))
        LOG.info("Subprocess Executing: {}".format(" ".join(commandLine)))
        retcode = subprocess.call(commandLine, stdout=outfh, stderr=errfh)
        outfh.close()
        errfh.close()
        if(retcode < 0):
            LOG.warning("Subprocess: {} terminated by signal {}".format(command,retcode))
            status=False
            return(status)
        elif(retcode > 0):
            LOG.warning("Subprocess: {} returned with exit code {}".format(command,retcode))
            status=False
            return(status)
        else:
            LOG.info("Subprocess: {} completed normally".format(command))
    except OSError as e:
        LOG.warning("Subprocess: {} failed".format(command))
        status=False
        return(status)

    return(status)

