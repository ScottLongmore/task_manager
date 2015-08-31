#!/usr/bin/python
"""
plgnGOES2TDF.py - GOES2TDF plug-in methods: TASKS, WORK, PURGE
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

# Local modules
import error_codes
from utils import *
import fileAction
import dirRE

LOG = logging.getLogger(__name__) #create the logger for this file

fcsts = range(0, 127, 6)

# Parameters
DTSFormat = "%Y%m%d%H"
ISODTSFormat = "%Y%m%dT%H"

# GOES plug-in methods

def PURGE(config, tasks):
    '''
    Removes tasks with DTS older than backward search datetime
    '''
    currentTasks = []
    for task in tasks:

        taskDTG = datetime.datetime.strptime(task['DTS'], ISODTSFormat)
        if taskDTG > config['meta']['bkwdDTG']:
            currentTasks.append(task)
        # else:
        #   LOG.info("Task datetime: {} older than backward search datetime: {}, removing".format(taskDTG.strftime(ISODTSFormat),config['meta']['bkwdDTG'].strftime(ISODTSFormat)))

    return(currentTasks)

def TASKS(config):

    meta = config['meta']
    plugin = config['plugin']
    inputs = config['inputs']['grib2']

    tasksLogFile = os.path.join(config['logDir'], "{}_TASKS_{}.log".format(config['name'], meta['runDTG'].strftime(ISODTSFormat)))
    tasksLogFH = open(tasksLogFile, "a")

    # Find task files
    FA = fileAction.fileAction(config)
    inputFiles = FA.findInputFiles(['grib2'])
    # Put GOES meta, files, and channels, into task list
    records = {}
    filepaths = inputFiles['grib2']
    for filepath in filepaths:

        m = re.match(inputs['re'],os.path.basename(filepath))
        fields = m.groupdict()
        DTS = fields['DTS']
        DTG = datetime.datetime.strptime(DTS, DTSFormat)
        fcst = fields['fcst']
        file_id = "_".join([DTS,fcst])

        if file_id not in records:
              records[file_id] = collections.OrderedDict()
              records[file_id]['fcst'] = []
              records[file_id]['files'] = []

        records[file_id]['DTS'] = DTG.strftime(ISODTSFormat)
        records[file_id]['fcst'].append(fcst)
        records[file_id]['files'].append(filepath)

    ids = records.keys()
    ids.sort()
    ids.reverse()

    tasks = []
    for file_id in ids:
        tasks.append(records[file_id])
    # Remove any older tasks than backward search datetime
    tasks = PURGE(config, tasks)

    tasksLogFH.close()
    return(tasks)

def WORK(config,task):

    plugin=config['plugin']
    inputs = config['inputs']['goes']
    taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)

    status=True
    diff = set(channels.keys()) - set(task['channels'])

    # Channel files are missing, exit
    if diff:
        LOG.info('Channels {} files are missing for datetime: {} satellite: {}, skipping'.format(",".join(diff),task['DTS'],task['satellite']))
        status=False

    # All GOES channels files are present for binary conversion
    else:

        satName=sats[task['satellite']]['name']
        satPosition=sats[task['satellite']]['position']
        LOG.info('Running task datetime: {} satellite: {} for sector: {} for channels {}'.format(task['DTS'],satName,task['sector']['name'],",".join(task['channels'])))
        workDir=os.path.join(str(config['workDirRoot']),task['DTS'],satName,task['sector']['name'])
        convDir=os.path.join(str(config['workDirRoot']),task['DTS'])

        # Creating work directory
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

        # Link GOES info file
        try:
            file=os.path.basename(plugin['goesInfoFile'])
            linkFilePath=os.path.join(workDir,file)
            LOG.info("Linking GOES info file: {} to {}".format(plugin['goesInfoFile'],linkFilePath))
            os.symlink(plugin['goesInfoFile'],linkFilePath)
        except:
            LOG.warning("Unable to link {} to {}".format(plugin['goesInfoFile'],linkFilePath))
            status=False
            return(status)

        # Link GOES data files, create mcidas to binary manifest files, create binary outputfile names
        outputFiles={}
        for srcFilepath in task['files']:

            file=os.path.basename(srcFilepath)
            dstFilepath=os.path.join(workDir,file)
            match=re.match(inputs['re'],file)
            fields=match.groupdict()
            type=channels[fields['channel']]
            outputFiles[type]=[]

            # Link GOES data files
            try:
                LOG.info("Linking GOES file: {} to {}".format(srcFilepath,dstFilepath))
                os.symlink(srcFilepath,dstFilepath)
            except:
                LOG.warning("Unable to link GOES file {} to {}".format(srcFilepath, dstFilepath))
                status=False
                return(status)

            # Create GOES to binary manifest files: NUMBER_C01.TXT
            try:
                manifestFN=os.path.join(workDir,"NUMBER_C{}.TXT".format(fields['channel']))
                LOG.info("Creating GOES mcidas to binary manifest file {}".format(manifestFN))
                manifestFH=open(manifestFN,"w")
                manifestFH.write(file)
                manifestFH.close()
            except:
                LOG.warning("Unable to create GOES mcidas to binary manifest file {}".format(manifestFN))
                status=False
                return(status)

            # Create expected GOES binary output files
            try:
                for suffix in binSuffixes[type]:
                    outputFile="{}i{}.c{}.{}".format(fields['DTS'],fields['satellite'],fields['channel'],suffix)
                    outputFiles[type].append(outputFile)
            except:
                LOG.warning("Unable to create GOES mcidas binary output file list")
                status=False
                return(status)

        # Create GOES mcidas to binary path files
        try:
            mcidasFN=os.path.join(workDir,plugin['mcidasPathFile'])
            LOG.info("Creating GOES mcidas path files: {}".format(mcidasFN))
            mcidasFH=open(mcidasFN,"w")
            mcidasFH.write(workDir+'/')
            mcidasFH.close()
            binaryFN=os.path.join(workDir,plugin['binaryPathFile'])
            LOG.info("Creating GOES binary path files: {}".format(binaryFN))
            binaryFH=open(binaryFN,"w")
            binaryFH.write(workDir+'/')
            binaryFH.close()
        except:
            LOG.warning("Unable to create GOES mcidas to binary path files")
            status=False
            return(status)

        # Run GOES_VIS mcidas to binary converter
        commandArgs=[plugin['visToBinExe']]
        args=[]
        if not execute(commandArgs,args,workDir):
            LOG.warning("Execute failed for {}".format(plugin['visToBinExe']))
            status=False
            return(status)

        # Run GOES_IR mcidas to binary converter
        commandArgs=[plugin['irToBinExe']]
        args=[]
        if not execute(commandArgs,args,workDir):
            LOG.warning("Execute failed for {}".format(plugin['irToBinExe']))
            status=False
            return(status)

        # Verify and rename output files
        for type in outputFiles:
            for outputFile in outputFiles[type]:
                if not os.path.isfile(outputFile):
                    LOG.warning("GOES {} to binary output file not found: {}".format(type,outputFile))
                    status=False
                    return(status)
                try:
                    basename, ext =os.path.splitext(outputFile)
                    newOutputFile="{}.{}{}".format(basename,task['sector']['name'],ext)
                    outputFilePath=os.path.join(workDir,outputFile)
                    newOutputFilePath=os.path.join(workDir,newOutputFile)
                    LOG.info("Renaming GOES {} output file: {} to {}".format(type,outputFilePath,newOutputFilePath))
                    os.rename(outputFilePath,newOutputFilePath)
                except:
                    LOG.warning("Unable to rename GOES {} output file: {} to {}".format(type,outputFile,newOutputFile))
                    status=False
                    return(status)

        # Run GOES binary to TDF converter 
        ######################
        # Operational
        # $satfile_path = $ARGV[0];
        # $yyyy         = $ARGV[1]
        # $ddd          = $ARGV[2]; 
        # $hhmm         = $ARGV[3];
        # $sat          = $ARGV[4];
        # $scan         = $ARGV[5];
        # $output_path  = $ARGV[6];
        ######################

        commandArgs=[plugin['binToTDFExe']]
        args=[convDir,taskDTG.strftime("%Y"),taskDTG.strftime("%j"),taskDTG.strftime("%H%M"),satPosition,task['sector']['name'],workDir]
        if not execute(commandArgs,args,workDir):
            LOG.warning("Execute failed for {}".format(plugin['binToTDFExe']))
            status=False
            return(status)

    return(status)

def execute(commandArgs,args,workDir):

    command=commandArgs[-1]

    commandLine=[]
    commandLine.extend(commandArgs)
    commandLine.extend(args)

    status=True
    try:
        base, ext =os.path.splitext(os.path.basename(command))
        logFile=os.path.join(workDir,base+".log")
        errFile=os.path.join(workDir,base+".err")
        logfh=open(logFile,'w')
        errfh=open(errFile,'w')
        LOG.info("Log File: {}".format(logFile))
        LOG.info("Error File: {}".format(errFile))
        LOG.info("Subprocess Executing: {}".format(" ".join(commandLine)))
        retcode = subprocess.call(commandLine, stdout=logfh, stderr=errfh)
        logfh.close()
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

'''
        # GOES IR processing
            # Link Mcidas files to working directory
            # Create goes_vis converter configuration files in working directory 
            # (goes_mcidas.txt, goes_binary.txt, channel list files e.g. NUMBER_C01.TXT
            # CD to working directoryi, run goes_vis converter 
            # Rename config files (for archive)
 
        # Run Steve's terrascan binary to TDF script
'''


