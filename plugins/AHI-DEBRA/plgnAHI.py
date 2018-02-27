#!/usr/bin/python
"""
  plgnAHI.py - plug-in methods: TASKS, WORK, PURGE
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
import zipfile
import shutil
import pprint

# Local modules
import error_codes
import fileAction
import dirRE

LOG = logging.getLogger(__name__)  # create the logger for this file
LOG.setLevel(logging.INFO)

# Parameters
DTSFormat = "%Y%m%d_%H%M"
ISODTSFormat = "%Y%m%dT%H%M%S"

bandIds={'01': {'res':'10'},
         '02': {'res':'10'},
         '03': {'res':'05'},
         '04': {'res':'10'},
         '05': {'res':'20'},
         '06': {'res':'20'},
         '07': {'res':'20'}, 
         '08': {'res':'20'},
         '09': {'res':'20'},
         '10': {'res':'20'},
         '11': {'res':'20'},
         '12': {'res':'20'},
         '13': {'res':'20'},
         '14': {'res':'20'},
         '15': {'res':'20'},
         '16': {'res':'20'}
        }
scans=xrange(1,11)


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
    inputs = config['inputs']['AHI']

    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(config)

    tasksLogFile = os.path.join(config['logDir'],"{}_TASKS_{}.log".format(config['name'], meta['runDTG'].strftime(ISODTSFormat)))
    tasksLogFH = open(tasksLogFile, "a")

    # Find task files
    FA = fileAction.fileAction(config)
    inputFiles = FA.findInputFiles(['AHI'])
    records = {}
    filepaths = inputFiles['AHI']
 
    for filepath in filepaths:

        m = re.match(inputs['re'], os.path.basename(filepath))
        fields = m.groupdict()
        DTS = fields['DTS']
        DTG = datetime.datetime.strptime(DTS, DTSFormat)
        ISODTS = DTG.strftime(ISODTSFormat)
        taskId = DTG.strftime("%Y%m%d%H%M")

        if taskId not in records:
            records[taskId] = collections.OrderedDict()

        records[taskId]['DTS'] = ISODTS 
        if 'files' not in records[taskId]:
            records[taskId]['files'] = [] 
	records[taskId]['files'].append(filepath)

    taskIds = records.keys()
    taskIds.sort()
    taskIds.reverse()

    tasks = []
    for taskId in taskIds:

        # Initlize band/scan/res verification structure 
        vBandIds=copy.deepcopy(bandIds)
        for bandId in vBandIds:
            vBandIds[bandId]['scans']=[]

        # Generate and verify list of data files needed for given DTG e.g. 16 bands x 10 scans = 160 files
        for filepath in records[taskId]['files']:
            match=re.match(inputs['re'], os.path.basename(filepath))
            fields = match.groupdict()
            band=fields['BAND']
            scan=int(fields['SCAN'][:2])
            res=fields['RES']


            # Verify all scans are present for particular band/resolution
            if band in vBandIds and scan in scans:
                if res == vBandIds[band]['res']:
                    vBandIds[band]['scans'].append(scan)
                    # print("{} {} {} {}".format(band,scan,res,filepath))

        # Verify all bands for all scans
        missing={}
        for bandId in vBandIds:
	    if len(vBandIds[bandId]['scans'])!=len(scans):
               scanDiff=list(set(scans) - set(vBandIds[bandId]['scans']))
               # print("{} {}".format(bandId,scanDiff))
               missing[bandId]=scanDiff
               # missing[bandId]=[]
               # missing[bandId].extend(scanDiff)
                 

        # Add task if all bands/scans are present
        # print("{} {}".format(bands,len(vBandIds)))
        if not missing: 
           tasksLogFH.write("All Bands/Scans are present for taskId {}\n".format(taskId))
           tasks.append(records[taskId])
        else:
           tasksLogFH.write("Bands/Scans are missing for taskId {}, skipping...\n".format(taskId))
           for bandId in missing:
               tasksLogFH.write("Band: {} Scans: {}\n".format(bandId,','.join(map(str,missing[bandId]))))

        del missing
        del vBandIds

    # Remove any older tasks than backward search datetime
    tasks = PURGE(config, tasks)

    tasksLogFH.write("Number of Tasks: {}\n".format(len(tasks)))

    tasksLogFH.close()
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
    status=True   
    meta = config['meta']
    inputs = config['inputs']['AHI']
    plugin=config['plugin']

    workLogFile = os.path.join(config['logDir'],"{}_WORK_{}.log".format(config['name'], meta['runDTG'].strftime(ISODTSFormat)))
    workLogFH = open(workLogFile, "a")

    taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)
  

    LOG.info('Creating working directories')

    # Create work directory 
    workDir=os.path.join(str(config['workDirRoot']),task['DTS'])
    if not os.path.exists(workDir):
       LOG.debug('Creating working directory: {}'.format(workDir))
       try:
           os.makedirs(workDir)
       except:
           LOG.warning("Unable to create work dir {}".format(workDir))
           status=False
           return(status)

    # CD to work directory
    try:
        LOG.debug('Changing to working directory: {}'.format(workDir))
        os.chdir(workDir)
    except:
        LOG.warning("Unable to change to work dir: {}".format(workDir))
        status=False
        return(status)

    # Create diagnostics directory 
    diagDir=os.path.join(workDir,'diag')
    if not os.path.exists(diagDir):
       LOG.debug('Creating diagnostics sub-directory: {}'.format(diagDir))
       try:
           os.makedirs(diagDir)
       except:
           LOG.warning("Unable to create diag dir {}".format(diagDir))
           status=False
           return(status)

    # Unzip files into working directory 
    LOG.info('Uncompressing AHI data into work directory')
    dataDir=os.path.join(workDir,'data')
    try:
        os.makedirs(dataDir)
    except:
        LOG.warning("Unable to create data dir {}".format(dataDir))
        status=False
        return(status)
    
    for filepath in task['files']:

       # Convert binary files to TDF file
       sourceFile=os.path.basename(filepath)
       targetFile,ext=os.path.splitext(sourceFile)
       targetFilepath=os.path.join(dataDir,targetFile)
       stderrFilepath=os.path.join(diagDir,"{}_{}.stderr".format(os.path.basename(plugin['decompressExe']),targetFile))
       commandList=[plugin['decompressExe']]
       commandArgs=['-ckd',filepath]
       commandID=taskDTG.strftime(DTSFormat)
       
       if not execute(commandList,commandArgs,commandID,workDir,stdoutFile=targetFilepath,stderrFile=stderrFilepath):
           LOG.warning("Execute failed for {}".format(plugin['decompressExe']))
           status=False
           return(status)
   
    # TDF conversion
    LOG.info('Converting specified sector binary to TDF files')
    tdfDir=str(plugin['tdfDir'])
    for sector in plugin['sectors']:

       LOG.info('Converting {} sector to TDF file'.format(sector))

       # Create sector sub work directory
       sectorWorkDir=os.path.join(workDir,sector)
       try:
           os.makedirs(sectorWorkDir)
       except:
           LOG.warning("Unable to create sector dir {}".format(sectorWorkDir))

       # Call TDF converter for given output sector
       commandList=[plugin['binToTDFScp']]
       commandArgs=[dataDir,taskDTG.strftime("%Y"),taskDTG.strftime("%m"),taskDTG.strftime("%d"),taskDTG.strftime("%H"),taskDTG.strftime("%M"),
                    sector,plugin['binDir'],sectorWorkDir,tdfDir]
       commandID=taskDTG.strftime(DTSFormat)
       if not execute(commandList,commandArgs,commandID,workDir):
           LOG.warning("Execute failed for {}".format(plugin['binToTDFScp']))

       # Configure TDF output file
       tdfFile="{}.{}".format(taskDTG.strftime("%Y%m%d.%H%M"),plugin['tdfExt'])
       tdfFilePath=os.path.join(tdfDir,tdfFile)
       if not os.path.exists(tdfFilePath):
           LOG.warning("TDF file {} not generated".format(tdfFilePath))
       else:
           LOG.info("TDF file {} generated".format(tdfFilePath))

       # Run DEBRA processing script 
       commandList=[plugin['DEBRAScp']]
       commandArgs=[tdfFilePath,plugin['DEBRAScpDir'],plugin['imgDir'],sectorWorkDir]
       commandID=taskDTG.strftime(DTSFormat)
       if not execute(commandList,commandArgs,commandID,workDir):
           LOG.warning("Execute failed for {}".format(plugin['DEBRAScp']))
           status=False
           return(status)


    workLogFH.close()

    return(status)


def execute(commandList,commandArgs,commandID,workDir,stdoutFile='',stderrFile=''):

    command=commandList[-1]

    commandLine=[]
    commandLine.extend(commandList)
    commandLine.extend(commandArgs)

    status=True
    try:
        base, ext =os.path.splitext(os.path.basename(command))

        if not stdoutFile: 
           stdoutFile=os.path.join(workDir,"{}_{}.stdout".format(base,commandID))
        if not stderrFile:
           stderrFile=os.path.join(workDir,"{}_{}.stderr".format(base,commandID))

        outfh=open(stdoutFile,'w')
        errfh=open(stderrFile,'w')
        LOG.debug("STDOUT File: {}".format(stdoutFile))
        LOG.debug("STDERR File: {}".format(stderrFile))
        LOG.debug("Subprocess Executing: {}".format(" ".join(commandLine)))
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
            LOG.debug("Subprocess: {} completed normally".format(command))
    except OSError as e:
        LOG.warning("Subprocess: {} failed".format(command))
        status=False
        return(status)

    return(status)

