#!/usr/bin/python
"""
plgnGOES_GEOCOLOR.py - GOES geocolor plug-in methods: TASKS, WORK, PURGE
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
import shutil

# Local modules
import error_codes
from utils import *
import fileAction
import dirRE

LOG = logging.getLogger(__name__) #create the logger for this file

# Parameters 
sats={
     '13':{'name':'goes-east','position':'east','sat_name':'g13','sat_name_tdf':'goes-13','sensor_name':'gvar'},
     '15':{'name':'goes-west','position':'west','sat_name':'g15','sat_name_tdf':'goes-15','sensor_name':'gvar'}
}
channels={'01':'VIS','02':'IR','03':'IR','04':'IR','06':'IR'}
binSuffixes={
     'VIS':['lat.dat','lon.dat','sza.dat','ref.dat','le.txt'],
     'IR':['lat.dat','lon.dat','sza.dat','tb.dat','le.txt']
}
pix_size_VIS=1.0
pix_size_IR=4.0
geocolorSectors={
    'goes-east':{
        'full-disk':'full-disk',
        'nh-ext':'nh-ext'
    },
    'goes-west':{
        'full-disk':'full-disk',
        'nh':'nh-ext'
    }
}

DTSFormat="%Y%j%H%M%S"
ISODTSFormat="%Y%m%dT%H%M%S"

# GOES plug-in methods 

# GOES purge routine: removes tasks with DTS older than backward search datetime.
def PURGE(config,tasks):

    currentTasks=[]
    for task in tasks:

        taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)

        if taskDTG > config['meta']['bkwdDTG']: 
           currentTasks.append(task)
        # else:
        #   LOG.info("Task datetime: {} older than backward search datetime: {}, removing".format(taskDTG.strftime(ISODTSFormat),config['meta']['bkwdDTG'].strftime(ISODTSFormat)))

    return(currentTasks)

def TASKS(config):

    meta=config['meta']
    plugin=config['plugin']
    input=config['inputs']['goes']
      
    sectorsLogFile=plugin['sectorsLogFile']
    sectorsLogFH=open(sectorsLogFile,"a")

    tasksLogFile=os.path.join(config['logDir'],"{}_TASKS_{}.log".format(config['name'],meta['runDTG'].strftime(ISODTSFormat)))
    tasksLogFH=open(tasksLogFile,"a")

    headers=json.load(open(plugin['goesHeadersFile']),object_pairs_hook=collections.OrderedDict)
    sectors=json.load(open(plugin['goesSectorsFile']),object_pairs_hook=collections.OrderedDict)

    # Find task files
    FA=fileAction.fileAction(config)
    inputFiles=FA.findInputFiles(['goes'])

    # Put GOES meta, files, and channels, into task list 
    records={}
    filepaths=inputFiles['goes']
    for filepath in filepaths:
    
          m=re.match(input['re'],os.path.basename(filepath))
          fields=m.groupdict()
          prefix=fields['prefix']
          DTS=fields['DTS']
          DTG=datetime.datetime.strptime(DTS,DTSFormat)
          sat=fields['satellite']
          ch=fields['channel']
          id="_".join([DTS,sat])

          # Determine if mcidas binary file had a defined sector

          if sat not in sectors:
              tasksLogFH.write("Satellite: {} not defined for mcidas file: {}, skipping\n".format(sat,filepath)) 
              continue

          band=channels[ch]
          bands={}
          sectorIds={}
          sectorLines={}
          sectorElems={}
          if band in headers: 

              header=collections.OrderedDict()
              header=copy.deepcopy(headers[band])
              if not readBinaryFileHeader(header,filepath):
                  msg='Error reading binary file: {}'.format(filePath)
                  error(LOG,msg,error_codes.EX_USAGE)
              
              if set(['num_line','num_elem']) <= set(header):

                  nLines=header['num_line']['values'][0]
                  nElems=header['num_elem']['values'][0]
                  sectorId="{}x{}".format(nLines,nElems)
                  if sectorId in sectors[sat]:
                      sectorName=sectors[sat][sectorId]['name']
                      bands[band]=band
                      sectorIds[band]=sectorId
                      sectorLines[band]=nLines
                      sectorElems[band]=nElems
                      sectorsLogFH.write("{} {} {}x{} defined as Sector: {} for mcidas file: {}\n".format(DTS, sat, nLines,nElems,sectorName,filepath)) 
                  else:
                      tasksLogFH.write("Sector: {} not defined for mcidas file: {}, skipping\n".format(sectorId,filepath)) 
                      sectorsLogFH.write("{} {} {}x{} not defined for mcidas file: {}\n".format(DTS, sat, nLines,nElems,filepath)) 
                      continue
              else:
                  tasksLogFH.write("Line/Elements fields not found in mcidas file: {}, skipping\n".format(filepath)) 
                  continue
          else:
              tasksLogFH.write("Channel: {} not defined for mcidas file: {}, skipping\n".format(ch,filepath)) 
              continue

          if id not in records:
              records[id]=collections.OrderedDict()
              records[id]['DTS']=DTG.strftime(ISODTSFormat)
              records[id]['satellite']=sat
              records[id]['sector']=collections.OrderedDict()
              records[id]['sector']['name']=sectorName
              records[id]['sector']['band']=collections.OrderedDict()
              records[id]['channels']=[]
              records[id]['files']=[]
    
          records[id]['channels'].append(ch)
          records[id]['files'].append(filepath)

          for band in bands:
              if band not in records[id]['sector']['band']:
                  records[id]['sector']['band'][band]=collections.OrderedDict()
              records[id]['sector']['band'][band]['id']=sectorId
              records[id]['sector']['band'][band]['lines']=nLines
              records[id]['sector']['band'][band]['elems']=nElems
    
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

    plugin=config['plugin']
    input=config['inputs']['goes']
    taskDTG=datetime.datetime.strptime(task['DTS'],ISODTSFormat)

    # print json.dumps(task,indent=4)

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
        sat_name=sats[task['satellite']]['sat_name']
	sat_name_tdf=sats[task['satellite']]['sat_name_tdf']
        sensor_name=sats[task['satellite']]['sensor_name']
        scan=task['sector']['name']
        visLines= task['sector']['band']['VIS']['lines']
        visElems= task['sector']['band']['VIS']['elems']
        irLines= task['sector']['band']['IR']['lines']
        irElems= task['sector']['band']['IR']['elems']

        LOG.info('Running task datetime: {} satellite: {} for sector: {} for channels {}'.format(task['DTS'],satName,task['sector']['name'],",".join(task['channels'])))

        convDir=os.path.join(str(config['workDirRoot']),"convert",task['DTS'])
        workDir=os.path.join(convDir,satName,task['sector']['name'])
        tdfDir=os.path.join(str(config['workDirRoot']),"tdf",satName,scan)
        imageDir=os.path.join(str(config['workDirRoot']),"image")
        imageWorkDir=os.path.join(imageDir,task['DTS'])
        outputDir=str(config['outputDir'])
        

        # Creating work directory
        if os.path.exists(workDir):
           LOG.info('Working directory already exists, incomplete job?, removing: {}'.format(workDir))
           try:
               shutil.rmtree(workDir)
           except:
               LOG.warning("Unable to remove previous work dir {}".format(workDir))
               status=False
               return(status)
        else:
           LOG.info('Creating working directory: {}'.format(workDir))
           try:
               os.makedirs(workDir)
           except:
               LOG.warning("Unable to create work dir {}".format(workDir))
               status=False
               return(status)

        if not os.path.exists(tdfDir):
           LOG.info('Creating terrascan (TDF) directory: {}'.format(tdfDir))
           try:
               os.makedirs(tdfDir)
           except:
               LOG.warning("Unable to create TDF dir {}".format(tdfDir))
               status=False
               return(status)

        if not os.path.exists(imageWorkDir):
           LOG.info('Creating image directory: {}'.format(imageWorkDir))
           try:
               os.makedirs(imageWorkDir)
           except:
               LOG.warning("Unable to create image dir {}".format(imageWorkDir))
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
        binOutputFiles={}
        for srcFilepath in task['files']:

            file=os.path.basename(srcFilepath)
            dstFilepath=os.path.join(workDir,file)
            match=re.match(input['re'],file)
            fields=match.groupdict()
            type=channels[fields['channel']]
            if type not in binOutputFiles:
                binOutputFiles[type]=[]

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
                    binOutputFile="{}.c{}.{}".format(fields['prefix'],fields['channel'],suffix)
                    binOutputFiles[type].append(binOutputFile)
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
        LOG.info("Running VIS mcidas area to binary converter: {}".format(plugin['visToBinExe']))
        commandArgs=[plugin['visToBinExe']]
        args=[]
        if not execute(commandArgs,args,workDir):
            LOG.warning("Execute failed for {}".format(plugin['visToBinExe']))
            status=False
            return(status)

        # Run GOES_IR mcidas to binary converter
        LOG.info("Running IR mcidas area to binary converter: {}".format(plugin['visToBinExe']))
        commandArgs=[plugin['irToBinExe']]
        args=[]
        if not execute(commandArgs,args,workDir):
            LOG.warning("Execute failed for {}".format(plugin['irToBinExe']))
            status=False
            return(status)

        # Verify and rename output files
        for type in binOutputFiles:
            for binOutputFile in binOutputFiles[type]:
                if not os.path.isfile(binOutputFile):
                    LOG.warning("GOES {} to binary output file not found: {}".format(type,binOutputFile))
                    status=False
                    return(status)
                try:
                    basename, ext =os.path.splitext(binOutputFile)
                    newOutputFile="{}.{}{}".format(basename,task['sector']['name'],ext)
                    binOutputFilePath=os.path.join(workDir,binOutputFile)
                    newOutputFilePath=os.path.join(workDir,newOutputFile)
                    LOG.info("Renaming GOES {} output file: {} to {}".format(type,binOutputFilePath,newOutputFilePath))
                    os.rename(binOutputFilePath,newOutputFilePath)
                except:
                    LOG.warning("Unable to rename GOES {} output file: {} to {}".format(type,binOutputFile,newOutputFile))
                    status=False
                    return(status)


        # Run binary to TDF converter
        binToTDFconfigFile=os.path.join(workDir,"{}_{}_{}_binToTDF.json".format(taskDTG.strftime(ISODTSFormat),satPosition,scan))
        LOG.info("Creating binary to TDF converter input JSON file: {}".format(binToTDFconfigFile))
        try:
        # Create binToTDF json input file
            binToTDFmeta={ 
                "satfile_path":convDir,
                "yyyy":taskDTG.strftime("%Y"),
                "ddd":taskDTG.strftime("%j"),
                "hhmm":taskDTG.strftime("%H%M"),
                "sat":satPosition,
                "scan":scan,
                "sat_name":sat_name,
                "sat_name_tdf":sat_name_tdf,
                "sensor_name":sensor_name,
                "lines_VIS": visLines,
                "samples_VIS": visElems,
                "pix_size_VIS": pix_size_VIS,
	        "lines_IR": irLines,
                "samples_IR": irElems, 
                "pix_size_IR": pix_size_IR, 
                "output_path":workDir
            }
            binToTDF_FH=open(binToTDFconfigFile,"w")
            binToTDF_FH.write(json.dumps(binToTDFmeta,indent=4))
            binToTDF_FH.close()
        except:
            LOG.warning("Unable to create {} config file: {} ".format(plugin['binToTDFExe'],binToTDFconfigFile))
            status=False
            return(status)

        LOG.info("Running binary to TDF converter: {}".format(plugin['binToTDFExe']))
        commandArgs=[plugin['binToTDFExe']]
        args=[binToTDFconfigFile]
        if not execute(commandArgs,args,workDir):
            LOG.warning("Execute failed for {}".format(plugin['binToTDFExe']))
            status=False
            return(status)

        visTDFOutputFile="{}.{}.{}.{}.VIS.tdf".format(taskDTG.strftime("%Y%m%d.%H%M"),sensor_name,sat_name,scan)
        visTDFOutputFilePath=os.path.join(workDir,visTDFOutputFile)
        visTDFOutputLinkPath=os.path.join(tdfDir,visTDFOutputFile)

        irTDFOutputFile="{}.{}.{}.{}.IR.tdf".format(taskDTG.strftime("%Y%m%d.%H%M"),sensor_name,sat_name,scan)
        irTDFOutputFilePath=os.path.join(workDir,irTDFOutputFile)
        irTDFOutputLinkPath=os.path.join(tdfDir,irTDFOutputFile)

        # Link TDF files to master terrascan satellite/sector directory
        LOG.info("Linking VIS/IR TDF files {}/{} to TDF dir: {}".format(visTDFOutputFile,irTDFOutputFile,tdfDir))
        try:
            # os.symlink(visTDFOutputFilePath,visTDFOutputLinkPath)
            # os.symlink(irTDFOutputFilePath,irTDFOutputLinkPath)
            shutil.move(visTDFOutputFilePath,visTDFOutputLinkPath)
            shutil.move(irTDFOutputFilePath,irTDFOutputLinkPath)
        except:
            LOG.warning("Unable to link VIS/IR TDF files: {} or {} to TDF dir {}".format(visTDFOutputFile,irTDFOutputFile,tdfDir))
            status=False
            return(status)

        # Run geocolor script for certain sectors
        # if satName in geocolorSectors:
        #      if scan in geocolorSectors[satName]:
        #          
        #          LOG.info("Running geocolor programs: {}".format(plugin['geocolorExe']))
        #          commandArgs=[plugin['geocolorExe']]
        #          args=[visTDFOutputLinkPath, irTDFOutputLinkPath, scan, imageWorkDir]
        #          if not execute(commandArgs,args,imageWorkDir):
        #              LOG.warning("Execute failed for {}".format(plugin['geocolorExe']))
        #              status=False
        #              return(status)

        #          for root, subFolders, files in os.walk(imageWorkDir):
        #              for file in files:
        #                  if re.match("^.*\.gif$",file):
        #                      # os.symlink(os.path.join(root,file),os.path.join(outputDir,file)) 
        #                      shutil.move(os.path.join(root,file),os.path.join(outputDir,file)) 

        #      else:
        #          LOG.info("Geocolor sector: {} for satellite {} not defined, skipped".format(scan,satName))


    return(status)

