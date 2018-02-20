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
import pprint

# Local modules
import utils
import error_codes
import fileAction
import dirRE

LOG = logging.getLogger(__name__)  # create the logger for this file

pp = pprint.PrettyPrinter(indent=2)

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
                 'DTS':eDTG.strftime(ISODTSFormat),
		 'sDTS':sDTG.strftime(ISODTSFormat),
		 'eDTS':eDTG.strftime(ISODTSFormat),
                 'sFile':fileDTGs[sDTG],
                 'eFile':fileDTGs[eDTG]
                }
           tasks.append(task)
           #LOG.info("For task: {}".format(task['eDTS']))
	   #LOG.info("Adding start File: {}".format(task['sFile'])) 
           #LOG.info("Adding end File: {}".format(task['eFile']))
        else:
           LOG.warning("Delta: {} out of range".format(delta.total_seconds()))
           LOG.warning("For file: {}".format(fileDTGs[sDTG]))
           LOG.warning("And file: {}".format(fileDTGs[eDTG]))

    # Remove any older tasks than backward search datetime
    LOG.info("Initial {} TASKS created: [{}]".format(config['name'],len(tasks)))

    tasks = PURGE(config, tasks)

    LOG.info("{} TASKS created: [{}]".format(config['name'],len(tasks)))
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

    # Create work directory 
    workDir=os.path.join(str(config['workDirRoot']),task['DTS'])
    inputDir=os.path.join(workDir,plugin['inputSubDir'])
    utils.workDir(inputDir)
    outputDir=os.path.join(workDir,plugin['outputSubDir'])
    utils.workDir(outputDir)

    # CD to work directory
    utils.cdDir(workDir)

    # Link task image files to working directory
    try:
        LOG.info("Linking start image file: {}".format(task['sFile']))
        utils.linkFile(os.path.dirname(task['sFile']),os.path.basename(task['sFile']),inputDir)
        LOG.info("Linking end image file: {}".format(task['eFile']))
        utils.linkFile(os.path.dirname(task['eFile']),os.path.basename(task['eFile']),inputDir)
    except:
        LOG.warning("Unable to link image files")
        status=False
        return(status)

    # Executing createBFImages
    try:
        commandList=map(str,(plugin['pythonExe'],plugin['createBFImagesExe']))
        commandArgs=map(str,('-c',plugin['createBFImagesCfg'],'-t',plugin['timeStep'],'-f',inputs['fileFormat'],'-s',inputDir,'-o',outputDir))
        commandID=taskDTG.strftime(DTSFormat)
        LOG.info("Executing: {}".format(" ".join(commandList+commandArgs)))
        status=utils.execute(commandList,commandArgs,commandID,workDir)
    except:
        LOG.warning("Unable to execute: {}".format(" ".join(map(str,(commandList+commandArgs))))) 
        status=False
        return(status)

    if not status:
        LOG.warning("Execute failed for {}".format(plugin['createBFImagesExe']))
        status=False
        return(status)

    # Move created images to image directory
    inputName=config['name']
    outputs={
      "inputs": {
        inputName: {
          "dirs":[workDir],
          "re":inputs['re']
        }
      }
    }
    FA = fileAction.fileAction(outputs)
    filepaths = FA.findInputFiles([inputName])[inputName]
    for filepath in filepaths:
        try:
            m = re.match(inputs['re'], os.path.basename(filepath))
            fields = m.groupdict()
            fileDTS = fields['DTS']
            fileDTG=datetime.datetime.strptime(fileDTS,DTSFormat)
        except:
            LOG.warning("Unable to extract datetime from image output file: {}".format(filepath))
            status=False
            return(status)
        imageDir=os.path.join(plugin['imageDir'],fileDTG.strftime("%Y%m%d"))
        if not os.path.exists(imageDir):
            utils.workDir(imageDir)
           
        LOG.info("Linking output image file: {} to {}".format(os.path.basename(filepath),imageDir))
        utils.linkFile(os.path.dirname(filepath),os.path.basename(filepath),imageDir)

    return(status)

