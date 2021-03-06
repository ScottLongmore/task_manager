taskSchema={
    "$schema": "http://json-schema.org/draft-04/schema#", 
    "required": [
        "name", 
        "workDirRoot", 
        "logDir", 
        "completeTaskFile", 
        "primeTasksKey", 
        "sortReverseOption", 
        "plugin", 
        "meta", 
        "inputs"
    ], 
    "type": "object", 
    "description": "runTask Schema", 
    "properties": {
        "inputs": {
            "type": "object"
        }, 
        "meta": {
            "required": [
                "bkwdDelta"
            ], 
            "type": "object", 
            "properties": {
                "DTGfrmts": {
                    "type": "object"
                }, 
                "bkwdDelta": {
                    "type": "integer"
                }
            }
        }, 
        "sortReverseOption": {
            "type": "boolean"
        }, 
        "name": {
            "type": "string"
        }, 
        "plugin": {
            "required": [
                "module", 
                "purge", 
                "tasks", 
                "work"
            ], 
            "type": "object", 
            "properties": {
                "purge": {
                    "type": "string"
                }, 
                "tasks": {
                    "type": "string"
                }, 
                "work": {
                    "type": "string"
                }, 
                "module": {
                    "type": "string"
                }
            }
        }, 
        "completeTaskFile": {
            "type": "string"
        }, 
        "primeTasksKey": {
            "type": "string"
        }, 
        "logDir": {
            "type": "string"
        }, 
        "workDirRoot": {
            "type": "string"
        }
    }
}

completedSchema={
    "items": {
        "type": "object"
    }, 
    "$schema": "http://json-schema.org/draft-04/schema#", 
    "type": "array", 
    "description": "task schema"
}
