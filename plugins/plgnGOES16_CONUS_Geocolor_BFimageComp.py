#!/usr/bin/python
"""
  plgnGOES16_CONUS_Geocolor_BFimageComp.py - plug-in methods: TASKS, WORK, PURGE
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
import json

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
   
    LOG.info("Starting {} TASKS creation".format(config['name']))

    # Get geocolor butterflow working directories 
    inputId='GOES16_CONUS_Geocolor_BF'
    inputs = config['inputs'][inputId]
    geoColorDirRE=dirRE.dirRE(inputs['dirs'][0])
    dirpaths=geoColorDirRE.getDirs()

    workConfig=copy.deepcopy(config)
    workGeocolor = workConfig['inputs'][inputId]

    compImages=[]
    for dirpath in dirpaths:

        # Determine if dirpath DTG is beyond backDTG
        dirpathRE=inputs['dirs'][0].replace('^','')
        dirpathRE=dirpathRE.replace('$','')
        dirpathRE="^{}$".format(dirpathRE)
        dirpathMatch=re.match(dirpathRE,dirpath)
        dirpathFields=dirpathMatch.groupdict()
        dirpathDTG=datetime.datetime.strptime(dirpathFields['ISODTS'],ISODTSFormat)
        if dirpathDTG < meta['bkwdDTG']:
             # LOG.info("Directory DTG {} is beyond search window: {}".format(dirpathDTG,meta['bkwdDTG']))
             # LOG.info("{}".format(dirpath))
             continue

        startDTG=None
        endDTG=None
        
        # Get input geocolor files
        inputPath=os.path.join(dirpath,workGeocolor['inputSubDir'])
	workGeocolor['dirs'][0]=inputPath
        inputFA = fileAction.fileAction(workConfig)
	inputFilepaths = inputFA.findInputFiles([inputId])[inputId]

        # Get output butterflow geocolor files
        outputPath=os.path.join(dirpath,workGeocolor['outputSubDir'])
        workGeocolor['dirs'][0]=outputPath
        outputFA = fileAction.fileAction(workConfig)
	outputFilepaths = inputFA.findInputFiles([inputId])[inputId]

        if inputFilepaths and outputFilepaths: 

            startFilepath=None
            endFilepath=None

            for inputFilepath in inputFilepaths:
 
                try:
                    inputMatch=re.match(workGeocolor['re'],os.path.basename(inputFilepath))
                    inputFields=inputMatch.groupdict()
                    dtg=datetime.datetime.strptime(inputFields['DTS'],DTSFormat)
                    if not startDTG:
                       startDTG = dtg
                       startFilepath=inputFilepath
                    elif dtg < startDTG:
                       endDTG = startDTG
                       startDTG = dtg
                       endFilepath=startFilepath
                       startFilepath=inputFilepath
                    else:
                       endDTG = dtg
                       endFilepath=inputFilepath
                except:
                   LOG.warning("Problem extracting datetime from {}".format(inputFilepath))
                   traceback.print_exc(file=sys.stderr)
                   continue

            if startDTG and endDTG:

                # Add original and butteflow images to compImages struct
                for outputFilepath in outputFilepaths: 
     
                    outputMatch=re.match(inputs['re'],os.path.basename(outputFilepath))
                    outputFields=outputMatch.groupdict()
                    outputDTG=datetime.datetime.strptime(outputFields['DTS'],DTSFormat)
                    compImage={
                              "image1":startFilepath,
                              "title1":startDTG.strftime("%Y-%m-%d %H:%M:%S"),
                              "image2":outputFilepath,
                              "title2":outputDTG.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    compImages.append(compImage)
                    
            else:
                LOG.warning("Start and end datetimes not initialized for {}, continuing".format(dirpath))
                continue
 
    # Create task for current run
    tasks = []
    task={
         'DTS':meta['runDTG'].strftime(ISODTSFormat),
         'images':compImages
    }
    tasks.append(task)

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
    inputs = config['inputs']['GOES16_CONUS_Geocolor_BF']
    plugin=config['plugin']

    taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)
  
    LOG.info("Starting {} WORK for task: {}".format(config['name'],task['DTS']))
    status = True 

    # Create work directory 
    workDir=os.path.join(str(config['workDirRoot']),task['DTS'])
    utils.workDir(workDir)

    # CD to work directory
    utils.cdDir(workDir)

    # Write image comparison configuration file
    imageConfig=copy.deepcopy(plugin['imageCompConfig'])
    imageConfig['workDir']=workDir
    imageConfig['ffmpeg']['imagesToMovieOpts']['movie']="{}.{}".format(task['DTS'],imageConfig['ffmpeg']['imagesToMovieOpts']['movie'])
    imageConfigFile="{}_config.json".format(task['DTS'])
    imageConfigFilepath=os.path.join(workDir,imageConfigFile)
    imageConfigFH=open(imageConfigFilepath,'w')
    imageConfigFH.write(json.dumps(imageConfig, indent=2))
    imageConfigFH.close()

    # Write image comparison list JSON file
    imageListFile="{}_list.json".format(task['DTS'])
    imageListFilepath=os.path.join(workDir,imageListFile)
    imageListFH=open(imageListFilepath,'w')
    imageListFH.write(json.dumps(task['images'], indent=2))
    imageListFH.close()

    # Executing compImages.py 
    try:
        commandList=map(str,(plugin['pythonExe'],plugin['imageCompExe']))
        commandArgs=map(str,('-c',imageConfigFilepath,'-l',imageListFilepath))
        commandID=taskDTG.strftime(DTSFormat)
        LOG.info("Executing: {}".format(" ".join(commandList+commandArgs)))
        status=utils.execute(commandList,commandArgs,commandID,workDir)
    except:
        LOG.warning("Unable to execute: {}".format(" ".join(map(str,(commandList+commandArgs))))) 
        status=False
        return(status)

    if not status:
        LOG.warning("Execute failed for {}".format(" ".join(map(str,(commandList+commandArgs)))))
        status=False
        return(status)

    '''
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
    '''

    return(status)

