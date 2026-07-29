gsFilNom = "modFaultLog.py" #Written in MicroPython for ESP32
VEERSION = "V001" #Original version
gsVEERSN = gsFilNom + " " + VEERSION #

import time

'''
Example use with ok range:
import modFaultlog
modFaultlog.reportNumericError(
    "health.bmi",
    fBmiValue,
    sUnit="kg/m2"
)
Then immediately add context (once or when max/min changes)
modFaultlog.reportContextError(
    "health.bmi",
    {
        "fHealthyMin": 18.5,
        "fHealthyMax": 24.9
    }
)

Displaying on a one line LCD example:
def onButtonUp():
    global iFaultIndex
    gOrder, _ = modFaultlog.getErrorSnapshot()
    if iFaultIndex > 0:
        iFaultIndex -= 1

def onButtonDown():
    global iFaultIndex
    gOrder, _ = modFaultlog.getErrorSnapshot()
    if iFaultIndex < len(gOrder) - 1:
        iFaultIndex += 1

def getFaultLineText():
    gOrder, gRecords = modFaultlog.getErrorSnapshot()
    if not gOrder:
        return "No faults"
    sKey = gOrder[iFaultIndex]
    rec = gRecords[sKey]
    # Numeric fault?
    if "iLastValue" in rec:
        return "{}: {}{}".format(
            sKey.split(".")[-1],
            rec["iLastValue"],
            rec.get("sUnit", "")
        )
    # Event / message fault
    if "sLastMessage" in rec:
        return rec["sLastMessage"]
    return sKey
'''

MAX_ERROR_RECORDS = 10

gErrorRecords = {}
gErrorOrder = []

def reportEventError(sErrorKey, sMessage):
    _reportCore(sErrorKey, sMessage=sMessage)

def reportNumericError(sErrorKey, iValue, sUnit="%"):
    _reportCore(sErrorKey, iValue=iValue, sUnit=sUnit, bNumeric=True)

def reportContextError(sErrorKey, dContext):
    _reportCore(sErrorKey, dContext=dContext)

def clearError(sErrorKey):
    if sErrorKey in gErrorRecords:
        del gErrorRecords[sErrorKey]
        gErrorOrder.remove(sErrorKey)

def getErrorSnapshot():
    return gErrorRecords, gErrorOrder

def _reportCore(sErrorKey, sMessage=None, iValue=None, sUnit=None, dContext=None, bNumeric=False):
    iNowMs = time.ticks_ms()
    if sErrorKey in gErrorRecords:
        rec = gErrorRecords[sErrorKey]
        rec["iCount"] += 1
        rec["iLastSeenMs"] = iNowMs
        if bNumeric:
            rec["iLastValue"] = iValue
            if iValue < rec["iMinValue"]:
                rec["iMinValue"] = iValue
            if iValue > rec["iMaxValue"]:
                rec["iMaxValue"] = iValue
        if dContext is not None:
            rec["dLastContext"] = dContext
        if sMessage is not None:
            rec["sLastMessage"] = sMessage
        return
    if len(gErrorOrder) >= MAX_ERROR_RECORDS:
        sOldestKey = gErrorOrder.pop(0)
        del gErrorRecords[sOldestKey]
    rec = {"iCount":1,"iFirstSeenMs":iNowMs,"iLastSeenMs":iNowMs}
    if sMessage is not None:
        rec["sLastMessage"] = sMessage
    if bNumeric:
        rec["iMinValue"]=iValue
        rec["iMaxValue"]=iValue
        rec["iLastValue"]=iValue
        rec["sUnit"]=sUnit
    if dContext is not None:
        rec["dLastContext"]=dContext
    gErrorRecords[sErrorKey]=rec
    gErrorOrder.append(sErrorKey)
