from __future__ import annotations

PROJECT_CREATE = "project:create"
PROJECT_UPDATE = "project:update"
PROJECT_OPEN = "project:open"
PROJECT_LIST = "project:list"
PROJECT_DELETE = "project:delete"
PROJECT_SCAN_FILES = "project:scanFiles"
PROJECT_GET_STATIONS = "project:getStations"

SETTINGS_GET = "settings:get"
SETTINGS_UPDATE = "settings:update"
SETTINGS_GET_DEFAULTS = "settings:getDefaults"

TASK_VALIDATE = "task:validate"
TASK_CREATE = "task:create"
TASK_START = "task:start"
TASK_PAUSE = "task:pause"
TASK_RESUME = "task:resume"
TASK_STOP = "task:stop"
TASK_LIST = "task:list"
TASK_GET = "task:get"
TASK_DELETE = "task:delete"
TASK_RETRY = "task:retry"
TASK_GET_LOGS = "task:getLogs"
TASK_SUBSCRIBE_PROGRESS = "task:subscribeProgress"

RESULT_LIST = "result:list"
RESULT_GET_SERIES = "result:getSeries"
RESULT_GET_GRID = "result:getGrid"
RESULT_GET_INTERMEDIATE = "result:getIntermediate"
RESULT_EXPORT = "result:export"

REPORT_PREVIEW = "report:preview"
REPORT_EXPORT = "report:export"
REPORT_LIST_TEMPLATES = "report:listTemplates"

TEMPLATE_LIST = "template:list"
TEMPLATE_GET = "template:get"
TEMPLATE_SAVE = "template:save"
TEMPLATE_DELETE = "template:delete"

ALL_CHANNELS = {
    PROJECT_CREATE,
    PROJECT_UPDATE,
    PROJECT_OPEN,
    PROJECT_LIST,
    PROJECT_DELETE,
    PROJECT_SCAN_FILES,
    PROJECT_GET_STATIONS,
    SETTINGS_GET,
    SETTINGS_UPDATE,
    SETTINGS_GET_DEFAULTS,
    TASK_VALIDATE,
    TASK_CREATE,
    TASK_START,
    TASK_PAUSE,
    TASK_RESUME,
    TASK_STOP,
    TASK_LIST,
    TASK_GET,
    TASK_DELETE,
    TASK_RETRY,
    TASK_GET_LOGS,
    TASK_SUBSCRIBE_PROGRESS,
    RESULT_LIST,
    RESULT_GET_SERIES,
    RESULT_GET_GRID,
    RESULT_GET_INTERMEDIATE,
    RESULT_EXPORT,
    REPORT_PREVIEW,
    REPORT_EXPORT,
    REPORT_LIST_TEMPLATES,
    TEMPLATE_LIST,
    TEMPLATE_GET,
    TEMPLATE_SAVE,
    TEMPLATE_DELETE,
}
