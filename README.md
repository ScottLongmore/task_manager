Task Manager v1.0.0 2015-09-24

Scott Longmore - developer
Chris Slocum - developer

Task Manager is an algorithm automation framework to build tasks for algorithms 
and execute those algorithms with created task data.

The framework currently utilized 3 main components:

* runTasks.py - the automation program the calls configuration specified task plugin module routines

* [name].json - the JSON configuration for the plugin module

* plgn[name].py - the plug-in module that defines:

                TASKS - task creation - builds tasks e.g. data files, parameters, etc 
                        inputs: config (dictionary from configuration JSON, and runTasks meta data)
                        output: list of tasks (dictionaries)
                WORK  - task algorithm execution - setups and runs algorithm(s) using task data
                        inputs: config (dictionary) and task (dictionary) 
                        output: True on success, False on fail 
                PURGE - purges tasks in <name>_completed.json file, could be used to purge old data as well. 

Directory Structure:

* scripts/ - hosts the runTasks.py, libTasks.py and linked python utility libraries
* lib/ - utility libraries including:
     - fileAction.py (file search regular expression module) 
     - dirRE.py (directory search regular expression module, used by fileAction.py) 
* etc/ - hosts the JSON schema validation files for runTasks configuration and completed files
* plugins/ - hosts examples of plugin modules (plgn<name>.py)and configuration files (<name>.json)