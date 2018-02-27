#!/usr/bin/python
"""
plgnDNBdestripe.py - DNB destripe plug-in methods: TASKS, WORK, PURGE
"""

# Stock modules
import sys
import os
import re
import copy
import shutil
import logging
import traceback
import datetime
import collections
import operator
import subprocess
import h5py
import numpy
from glob import glob
import json

# Local modules
import error_codes
from utils import *
import fileAction
import dirRE

LOG = logging.getLogger(__name__) #create the logger for this file

# Parameters 
DTSFormat="%Y%m%d%H%M%S"
ISODTSFormat="%Y%m%dT%H%M%S"
dnbExt='SVDNB'
geoExt='GDNBO'
pngExt='png'
failExt='fail'

# DNB destripe plug-in methods 

# Purge routine: removes tasks with DTS older than backward search datetime.
def PURGE(config,tasks):

    currentTasks=[]
    for task in tasks:

        taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)

        if taskDTG > config['meta']['bkwdDTG']: 
           currentTasks.append(task)
        # else:
        #   LOG.info("Task datetime: {} older than backward search datetime: {}, removing".\
        #            format(taskDTG.strftime(ISODTSFormat),config['meta']['bkwdDTG'].strftime(ISODTSFormat)))

    return(currentTasks)

def TASKS(config):

    meta=config['meta']
    plugin=config['plugin']
    dnbInput=config['inputs'][dnbExt]
    geoInput=config['inputs'][geoExt]

    tasksLogFile=os.path.join(config['logDir'],\
                              "{}_TASKS_{}.log".format(config['name'],meta['runDTG'].strftime(ISODTSFormat)))
    tasksLogFH=open(tasksLogFile,"a")

    # Find task files
    FA=fileAction.fileAction(config)
    geoFiles=FA.findInputFiles([geoExt])
    dnbFiles=FA.findInputFiles([dnbExt])

    # Create reference map for geoFiles
    geoMap={}
    for geoFile in geoFiles[geoExt]:

        m=re.match(geoInput['re'],os.path.basename(geoFile))
        fields=m.groupdict()

        key="_".join(map(fields.get, ('Date','BeginTime','EndTime','Orbit')))
        geoMap[key]=geoFile

    # Put SVDNB/GDNBO meta, files, and channels, into task list 
    # SVDNB_npp_d20160222_t1109139_e1110381_b22389_c20160222173632102868_noaa_ops.h5
    records={}
    for dnbFile in dnbFiles[dnbExt]:
    
        m=re.match(dnbInput['re'],os.path.basename(dnbFile))
        fields=m.groupdict()
        key="_".join(map(fields.get, ('Date','BeginTime','EndTime','Orbit')))
       
        # Determine if there is a corresponding geo file -- need the lunar zenith angle
        if key in geoMap:
            beginSecs=int(round((float(fields['BeginTime'][4:8])*60.0)/1000.0)) # convert fractional thousands precison seconds to seconds
            beginTime="{}{}".format(fields['BeginTime'][0:4],beginSecs)
            endSecs=int(round((float(fields['EndTime'][4:8])*60.0)/1000.0)) # convert fractional thousands precison seconds to seconds
            endTime="{}{}".format(fields['EndTime'][0:4],endSecs)
            DTS="{}{}".format(fields['Date'],beginTime)
            DTG=datetime.datetime.strptime(DTS,DTSFormat)
            geoFile=geoMap[key]
        else:
            continue 

        id=DTG.strftime(ISODTSFormat)
        records[id]={}
        records[id]['DTS']=id
        records[id]['dnbFile']=dnbFile
        records[id]['geoFile']=geoFile
        records[id]['beginTime']=beginTime
        records[id]['endTime']=endTime
        records[id]['timeFrame']="t{}_e{}".format(fields['BeginTime'],fields['EndTime'])
        
    ids=records.keys()
    ids.sort()
    ids.reverse()

    tasks=[]
    for id in ids:
        tasks.append(records[id])

    # Remove any older tasks than backward search datetime
    tasks=PURGE(config,tasks)

    tasksLogFH.close()

    return(tasks)

def WORK(config,task):

    status=True
    plugin=config['plugin']
    dnbInput=config['inputs'][dnbExt]
    taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)

    try:
        os.stat(task['dnbFile'])
    except:
        LOG.warning("Problem with DNB file: {}".format(task['dnbFile']))
        status=False
        return(status)
    try:
        os.stat(task['geoFile'])
    except:
        LOG.warning("Problem with geo file: {}".format(task['geoFile']))
        status=False
        return(status)

    # Determine SZA/MPA thresholds from configuration
    try:
         SZAthresholds=[float(f) for f in plugin['SolarZenithAngle'].keys()]
         SZAthresholds.sort()
         MPAthresholds=[float(f) for f in plugin['MoonPhaseAngle'].keys()]
         MPAthresholds.sort()
    except:
        LOG.warning("Problem creating Solar/Lunar thresholds")
        status=False
        return(status)


    # Read SZA/MPA from task geo-file
    SZA=read_hdf5(task['geoFile'],"/All_Data/VIIRS-DNB-GEO_All/SolarZenithAngle")
    MPA=read_hdf5(task['geoFile'],"/All_Data/VIIRS-DNB-GEO_All/MoonPhaseAngle")
    DNF=read_hdf5_attr(task['dnbFile'],"/Data_Products/VIIRS-DNB-SDR/VIIRS-DNB-SDR_Gran_0","N_Day_Night_Flag")

    SZAdims=SZA.shape
    SZAdim1center=int(SZAdims[0]/2)
    SZAdim2center=int(SZAdims[1]/2)
    LOG.info("SZA Dims {}, Center point: {},{}".format(SZA.shape,SZAdim1center,SZAdim2center))
    SZAcenter=SZA[SZAdim1center][SZAdim2center]
    LOG.info("SZA center value: {}".format(SZAcenter))
    LOG.info("Day/Night Flag: {}".format(DNF))

    # Determine destripe command line params from current SZA/MPA
    destripeParams={}
    if SZAcenter >= plugin['SZADayNightThreshold']:
#    if (SZA >= plugin['SZADayNightThreshold']).all():
        SolarPhase='night'
        for MPAthreshold in MPAthresholds:
            if MPA[0] < MPAthreshold:
               destripeParams=plugin['MoonPhaseAngle'][str(MPAthreshold)] 
               LOG.info("MPA: {} Threshold: {} Name: {}".format(MPA[0],MPAthreshold,destripeParams['name']))
               break
    else:
        SolarPhase='day'
        destripeParams=plugin['SolarZenithAngle']["0.0"] 

    LOG.info("DTS: {}".format(task['DTS']))
    LOG.info("DNB FILE: {}".format(task['dnbFile']))
    LOG.info("GEO FILE: {}".format(task['geoFile']))
    LOG.info("Solar Phase: {}".format(SolarPhase))
    LOG.info("Moon Phase Angle: {}".format(MPA[0]))
    LOG.info("Params: {}".format(json.dumps(destripeParams)))

    dnbDTS=taskDTG.strftime("%Y%m%d")
    workDir=os.path.join(config['workDirRoot'],dnbDTS,'hdf')
    LOG.info("Work Dir: {}".format(workDir))

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

    # Copy DNB file to work directory
    try:
        workDnbFile=os.path.join(workDir,os.path.basename(task['dnbFile']))
        LOG.info('Copying DNB file {} to {}'.format(task['dnbFile'],workDnbFile))
        shutil.copy(task['dnbFile'],workDnbFile)
        workGeoFile=os.path.join(workDir,os.path.basename(task['geoFile']))
        LOG.info('Copying geo file {} to {}'.format(task['geoFile'],workGeoFile))
        shutil.copy(task['geoFile'],workGeoFile)
    except:
        LOG.warning("Unable to copy dnb/geo files: {} {}".format(workDnbFile,workGeoFile))
        status=False
        return(status)

    # Run DNB destriper 
    commandArgs=[plugin['pythonEXE'],plugin['DNBdestripeGranuleEXE']]
    args=[config['workDirRoot'],dnbDTS,task['timeFrame'],destripeParams['name']]

    dnbFileBase,dnbFileExt=os.path.splitext(os.path.basename(task['dnbFile']))

    statFH=open(config['statFile'],"a") 

    logDir=os.path.join(workDir,'log')
    if not os.path.exists(logDir):
        os.makedirs(logDir)
    logFile=os.path.join(logDir,dnbFileBase+".log")

    errDir=os.path.join(workDir,'error')
    if not os.path.exists(errDir):
        os.makedirs(errDir)
    errFile=os.path.join(errDir,dnbFileBase+".err")

    LOG.info("Executing {} {}".format(" ".join(commandArgs)," ".join(args)))
    if not execute(commandArgs,args,logFile,errFile):
        LOG.warning("Execute failed for {}".format(plugin['DNBdestripeGranuleEXE']))
        LOG.warning("Check sub-process log file: {}".format(logFile))
        LOG.warning("Check sub-process error file: {}".format(errFile))
        statFH.write("FAIL: {} {} {} {} {} {}\n".format(task['DTS'],SolarPhase,MPA[0],destripeParams['name'],task['dnbFile'],errFile))
        try:
            failDir=os.path.join(workDir,failExt)
            if not os.path.exists(failDir):
                os.makedirs(failDir)

            failDnbFile=os.path.join(failDir,os.path.basename(workDnbFile))
            if not os.path.exists(failDnbFile):
                shutil.move(workDnbFile,failDnbFile)
            else: 
                os.remove(workDnbFile)

            failGeoFile=os.path.join(failDir,os.path.basename(workGeoFile))
            if not os.path.exists(failGeoFile):
                shutil.move(workGeoFile,failGeoFile)
            else: 
                os.remove(workGeoFile)
	except:
            LOG.warning("Unable to move dnb/geo files to fail directory")

        status=False
        return(status)
    else:
        # Move DNB/geo/png files to final output directoreis, add 'dst' to filename
        statFH.write("PASS: {} {} {} {} {} {}\n".format(task['DTS'],SolarPhase,MPA[0],destripeParams['name'],task['dnbFile'],errFile))
        try:
            workDnbDir=os.path.join(workDir,dnbExt)
            if not os.path.exists(workDnbDir):
                os.makedirs(workDnbDir)
            newWorkDnbFile=os.path.join(workDnbDir,dnbFileBase+"_dst"+dnbFileExt)
            shutil.move(workDnbFile,newWorkDnbFile)
	except:
            LOG.warning("Unable to move/rename dnb file: {} to {}".format(workDnbFile,newWorkDnbFile))

        try:
            workGeoDir=os.path.join(workDir,geoExt)
            if not os.path.exists(workGeoDir):
                os.makedirs(workGeoDir)
            geoFileBase,geoFileExt=os.path.splitext(os.path.basename(task['geoFile']))
            newWorkGeoFile=os.path.join(workGeoDir,geoFileBase+"_dst"+geoFileExt)
            shutil.move(workGeoFile,newWorkGeoFile)
	except:
            LOG.warning("Unable to move/rename geo file: {} to {}".format(workGeoFile,newWorkGeoFile))

        try:
            workPngFile=workDnbFile+"."+pngExt
            workPngDir=os.path.join(workDir,pngExt)
            if not os.path.exists(workPngDir):
                os.makedirs(workPngDir)
            newWorkPngFile=os.path.join(workPngDir,os.path.basename(workPngFile))
            shutil.move(workPngFile,newWorkPngFile)
	except:
            LOG.warning("Unable to move/rename png file: {} to {}".format(pngWorkFile,newWorkPngFile))

    statFH.close()

    return(status)

def execute(commandArgs,args,logFile,errFile):

    command=commandArgs[-1]

    commandLine=[]
    commandLine.extend(commandArgs)
    commandLine.extend(args)

    status=True
    try:
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

def read_hdf5(h5_file, dataset_name):

  #Check if file exists
  file_check = glob(h5_file)
  if len(file_check) != 1:
    print 'The file path '+h5_file+ ' is invalid'
    sys.exit(2)
  
  open_file = h5py.File(h5_file, 'r')
  data_node = open_file[dataset_name]
  dataset = data_node.value
  
  return (dataset)

def read_hdf5_attr(h5_file, dataset_name, attr_name):

  #Check if file exists
  file_check = glob(h5_file)
  if len(file_check) != 1:
    print 'The file path '+h5_file+ ' is invalid'
    sys.exit(2)

  open_file = h5py.File(h5_file, 'r')
  data_node = open_file[dataset_name]
  attr=data_node.attrs[attr_name]

  return (attr)
