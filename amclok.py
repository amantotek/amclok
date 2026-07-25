gsFilNom = "amclok.py" #Written in MicroPython for ESP32
VEERSION = "V015" #Use with modWiFi017.py or newer
gsVEERSN = gsFilNom + " " + VEERSION #

#Hardware: 2.8" ESP32-2432S028R ESP32 Display ILI9341
#Resistive Touchscreen TFT LCD Module 240×320 px
#ESP-WROOM-32 Development Board 
##Created Nov 2025
##Fades colours between Red (night for sleeping) and Blue (day to keep alert)
giKeepLCDon4Testeq1 = 0 #Operationally 0 but change to 1 
#For testing to keep LCD on set all "glBacklightControlPin.value" 1

#System imports
import time
import uasyncio as asyncio
import network
import machine
import ili9341 #use Display, color565 see our own reversed re-definition
from xglcd_font import XglcdFont
import utime

#Our module imports
from modWiFi import wifiConnect,start_config_portal #,wifiIsConnected V017 TestedOK
import modDateTime #Using: sGetLocalTimeString iGetLocalHour iGetLocalMinute
import modFaultLog

glX = 15 #top-left corner of the first digit. 
glY = 40 #top-left corner of the first large digit.
glScale = 50 #54
glThick = 7 #2=Double thick character stroke width

glDigitWidth = glScale
glDigitHeight = glScale * 2  # outline digits are 2 units tall
glSpacing = int(glDigitWidth * 1.3) #Gap from H1 to H2 and M1 to M2
glColonSpacing = int(glDigitWidth * 1.6)

iClearBound = glThick+2 #Margin around characters to allow for their thickness
glClearWidth = glSpacing + glColonSpacing + glSpacing*2 + iClearBound*2
glClearHeight = glDigitHeight + iClearBound*2
#print("DB89 w={} h={}".format(glClearWidth,glDigitHeight))
glClearX = glX - iClearBound
glClearY = glY - iClearBound

#Four below are output from get_digit_bbox using figure 8
gDigitMinX = 0
gDigitMinY = 0
gDigitWidth = glScale+2 #55
gDigitHeight = 115

gPrevHHMM = -1 #Special case for digitXorCompare4 to yield "1111" NoteQZ
gcRegion = None

# ---- CONFIG ----
CONFIG = {
    "HTTP_PORT": 80,
    "WDT_TIMEOUT_MS": 60000,  # watchdog timeout
}

#GLOBALS
glFon16 = None
glTfft = None

# PIR on IO22 (through your 3.3k resistor)
glPirInputPin = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_DOWN)
# Backlight on IO21 (output only, no more pin mode switching)
glBacklightControlPin = machine.Pin(21, machine.Pin.OUT)
BACKLIGHT_TIMEOUT_NITE = 20000   # 20 seconds
BACKLIGHT_TIMEOUT_DAY = 55000   # 55 seconds
giBaklitTimut = BACKLIGHT_TIMEOUT_DAY
glLastMotionTime = time.ticks_ms()

def color565(r, g, b):
    # This redefines this function
    # Convert from RGB → BGR565 for displays wired in BGR mode.
    return ((b & 0xF8) << 8) | ((g & 0xFC) << 3) | (r >> 3)

#gColurBlue = color565(0, 0, 255)
gColurRed = color565(255, 0, 0)
gColurWhite = color565(255, 255, 255)
gColurBlack = color565(0, 0, 0)
gColurNow = gColurRed  # red Only to initialise, will change with time of day
gColurSecs = gColurRed  # Only to initialise, normally red but white during day

# ---- Watchdog ----
async def wdt_task():
    wdt = machine.WDT(timeout=CONFIG["WDT_TIMEOUT_MS"])
    while True:
        wdt.feed()
        await asyncio.sleep(CONFIG["WDT_TIMEOUT_MS"]/2000)
        
# Digit segment definitions for a block-outline font
# Coordinates are normalized 0..1 in X (0 is at the top)
#and 0..2 in Y (tall digits)
# '1': [(0.5,0), (0.5,2)] simple horizontally centered 1
# '1': [(0.6,0),(0.6,2),(0.4,2),(0.8,2)], with base line
DIGIT_SEGMENTS = {
    '0': [(0,0),(0.9,0),(0.9,2),(0,2),(0,0)],
    '1': [(0.4,0.2),(0.6,0),(0.6,2),(0.4,2),(0.8,2)],
    '2': [(0,0),(0.9,0),(0.9,1),(0,1),(0,2),(0.9,2)],
    '3': [(0,0),(0.9,0),(0.9,1),(0.3,1),
          (0.9,1),(0.9,2),(0,2)],
    '4': [(0,0),(0,1),(0.9,1),(0.9,0),(0.9,2)],
    '5': [(0.9,0),(0,0),(0,1),(0.9,1),(0.9,2),(0,2)],
    '6': [(0.9,0),(0,0),(0,2),(0.9,2),(0.9,1),(0,1)],
    '7': [(0,0),(0.9,0),(0.6,2)],
    '8': [(0,1),(0.9,1),(0.9,0),(0,0),
          (0,2),(0.9,2),(0.9,1)],
    '9': [(0.9,2),(0.9,0),(0,0),(0,1),(0.9,1)],
    '-': [(0.1,1), (0.9,1)]
}

def initLCD():
    global glTfft,glFon16
    # Backlight
    backlight = machine.Pin(21, machine.Pin.OUT)
    backlight.on()
    spi = machine.SPI(1, baudrate=20000000, sck=machine.Pin(14), mosi=machine.Pin(13), miso=machine.Pin(12))
    # Display init (LANDSCAPE MODE: rotation = 1)
    glTfft = ili9341.Display(
        spi,
        cs=machine.Pin(15),
        dc=machine.Pin(2),
        rst=machine.Pin(4),
        width=320,
        height=240,
        rotation=0   #Landscape, must be 0, 90, 180 or 270
    )
    # Font
    glFon16 = XglcdFont('Unispace12x24.c', 12, 24)
    # Fill full screen black
    glTfft.fill_rectangle(0, 0, glTfft.width, glTfft.height, gColurBlack)
    
def draw_multiline_text(x, y, lines, coloeur):
    """Draw a list of text lines with automatic vertical spacing."""
    line_height = glFon16.height + 4  # small spacing
    for i, sLien in enumerate(lines):
        glTfft.draw_text(x, y + i * line_height, sLien, glFon16, coloeur)

def text2LCD(lineOrLines):
    iPosX = 20
    iPosY = 40

    # Clear previous text area
    glTfft.fill_rectangle(iPosX, iPosY, 200, 80, gColurBlack)

    if isinstance(lineOrLines, str):
        #Single line of text
        draw_multiline_text(iPosX, iPosY, [lineOrLines], gColurWhite)
        print(f"> {lineOrLines}")
    else:
        #List of text lines
        draw_multiline_text(iPosX, iPosY, lineOrLines, gColurWhite)
        for sLine in lineOrLines:
            print(f"> {sLine}")

async def pirBacklightTask():
    #NoteBL 2/3
    global glLastMotionTime
    glBacklightControlPin.value(1)   # start with screen off
    while True:
        if glPirInputPin.value() == 1:
            glLastMotionTime = time.ticks_ms()
            #print("DBmd Motion detected {}".format(glLastMotionTime))
            glBacklightControlPin.value(1)   # turn on backlight
        else:
            elapsed = time.ticks_diff(time.ticks_ms(), glLastMotionTime)
            if elapsed > giBaklitTimut:
                glBacklightControlPin.value(0)   # 0=turn off. timeout → off
        await asyncio.sleep(0.05)

def fade_color(iMinsSinceMidnite, start, duration, R_start): #, B_start, R_end, B_end):
    #iMinsSinceMidnite: Minutes since midnight
    #start: Minutes since midnight to start colour change sequence
    #duration: minutes to complete colour change between Red to Blue or Blue to Red
    #R=Red used for nightime B=Blue for daytime
    #0=No colour 255=full colour. To fade between Red/Blue we either have
    #start this function with R_start B_start R_end B_end 
    #0 255 255 0 for B -> R or 255 0 0 255 R -> B
    #INPUT R_start ensure either 0 or 255
    if R_start == 0:
      #B -> R pre night time evening
      B_start = 255
      R_end = 255
      B_end = 0
    else:
      #R -> B pre wake up morning
      R_start = 255
      B_start = 0
      R_end = 0
      B_end = 255
    #R_end = B_start
    #B_end = R_start
    if iMinsSinceMidnite <= start:
        return R_start, B_start
    if iMinsSinceMidnite >= start + duration:
        return R_end, B_end
    fZZ = (iMinsSinceMidnite - start) / duration
    Rnow = int(R_start + (R_end - R_start) * fZZ)
    Bnow = int(B_start + (B_end - B_start) * fZZ)
    return Rnow, Bnow
    
#---------------------------------    
# Large HH MM display
#---------------------------------    
def get_digit_bbox(digit):
    #Return (minX, minY, width, height) relative to digit origin (0,0).
    #Use only once or if size of large chars change to get blanking rectangle size
    segs = DIGIT_SEGMENTS[digit]
    minX =  99999
    minY =  99999
    maxX = -99999
    maxY = -99999
    for sx, sy in segs:
        px = int(sx * glScale)
        py = int(sy * glScale)

        minX = min(minX, px)
        minY = min(minY, py)
        maxX = max(maxX, px)
        maxY = max(maxY, py)
    # Account for line thickness
    width  = (maxX - minX) + glThick
    height = (maxY - minY) + glThick
    return minX, minY, width, height

async def time_display_task(x=50, y=80):
    # Async task to display time on LCD ----
    #Updates HH:MM on LCD once per minute.
    #Seconds drive a secondary display
    global glTfft,glClearWidth,glDigitHeight,gColurNow
    global giBaklitTimut,gColurSecs,gPrevHHMM
    prev_minute = None
    iCurrentSecond = 0 #In case no NTP time lock
    while True:
        year, month, day, hour, minute, second, iDayOfWeek, cDSTsuffixUBG = modDateTime.tzGetLocalDateTime()
        updateSecondsRow(second)
        if minute != prev_minute:
            prev_minute = minute
            #Minute changed. Only redraw on minute change
            #Draws bottom info line dateTextRow *** begin
            #Expand DST status
            if cDSTsuffixUBG == "U":
                sLongUBG = "NoDST"
            elif cDSTsuffixUBG == "B":
                sLongUBG = "BST"
            elif cDSTsuffixUBG == "G":
                sLongUBG = "GMT"
            else:
                sLongUBG = "???"
            #Lundo Mardo Merkredo Ĵaŭdo Vendredo Sabato Dimanĉo
            DAYS_3 = ("Mon/Lun", "Tue/Mar", "Wed/Mer", "Thu/Jau", "Fri/Ven", "Sat/Sab", "Sun/Dim")
            sMonTue = DAYS_3[iDayOfWeek - 1]
            sTxt = f"{gcRegion}  {sLongUBG}: {sMonTue} {day:02d} {month:02d} {year}"
            iXltor = 10 #Left to  right
            yiYDwn = gYdownSecondsBar + 30
            glTfft.fill_rectangle(iXltor, yiYDwn, 200, 32, gColurBlack)
            glTfft.draw_text(iXltor, yiYDwn, sTxt, glFon16, gColurSecs)
            #Draws bottom info line dateTextRow *** end
            sHHMM = f"{hour:02}{minute:02}"  # String hhmm
            iMins = hour * 60 + minute # minutes since midnight
            iMorningStartMins = 5*60 #05:00
            iDuratnMorning = 120 #mins
            iEveningStartMins = (22*60) + 5 #22:05
            iDuratnEvening = 35 #mins
            gColurSecs = gColurRed
            #We have from time of day 00:00 to 23:59 colour of clock display in 5 blocks
            #1) 00:00 to iMorningStartMins Red
            #2) iMorningStartMins to iMorningStartMins + iDuratnMorning Fade from Red to Blue
            #3) iMorningStartMins + iDuratnMorning to iEveningStartMins Blue
            #4) iEveningStartMins to iEveningStartMins + iDuratnEvening Fade from Blue to Red
            #5) iEveningStartMins + iDuratnEvening to 23:59 Red
            bDay = False
            if iMins < iMorningStartMins:
              iColrR, iColrB = 255, 0 #1 Red
              giBaklitTimut = BACKLIGHT_TIMEOUT_NITE
            elif iMorningStartMins <= iMins < iMorningStartMins + iDuratnMorning:
              iColrR, iColrB = fade_color(iMins, iMorningStartMins, iDuratnMorning, 255) #2 Fade from Red to Blue
              gPrevHHMM = -1 #During Fade we need to refresh all HHMM digits every minute NoteQZ
            elif iMorningStartMins + iDuratnMorning <= iMins < iEveningStartMins:
              #iColrR, iColrB = 0, 255 #3 Blue
              bDay = True
              giBaklitTimut = BACKLIGHT_TIMEOUT_DAY
              gColurSecs = gColurWhite
            elif iEveningStartMins <= iMins < iEveningStartMins + iDuratnEvening:
              iColrR, iColrB = fade_color(iMins, iEveningStartMins, iDuratnEvening, 0) #4 Fade from Blue to Red
              gPrevHHMM = -1 #Refresh all digits to get fade colour NoteQZ
            else:
              iColrR, iColrB = 255, 0 #Red (at this point, only one thing can be true) #5
              giBaklitTimut = BACKLIGHT_TIMEOUT_NITE
            
            if bDay:
                gColurNow = gColurWhite #or gColurBlue
            else:
                gColurNow = color565(iColrR, 0, iColrB)
            drawLargeHHMM(sHHMM, glX, glY)
        await asyncio.sleep(1)
        
def clear_digit(x, y):
    """Clear exactly one digit area at (x,y)."""
    glTfft.fill_rectangle(
        x + gDigitMinX,
        y + gDigitMinY,
        gDigitWidth,
        gDigitHeight,
        gColurBlack
    )
  
def digitXorCompare4(iFirst: int, iSecond: int) -> str:
    if iFirst < 0: return "1111" #Special initial case NoteQZ
    sResult = ""
    for iDiv in (1000, 100, 10, 1):
        iDigit1 = (iFirst // iDiv) % 10
        iDigit2 = (iSecond // iDiv) % 10
        sResult += '1' if (iDigit1 ^ iDigit2) else '0'
    return sResult
#print(digitXorCompare4(1234, 1564))  # 0110

def draw_digit(x, y, digit):
    """Draw one outline digit at (x,y)."""
    global glScale,glTfft,glThick,gColurNow
    segs = DIGIT_SEGMENTS[digit]
    for i in range(len(segs)-1):
        x1 = int(x + segs[i][0] * glScale)
        y1 = int(y + segs[i][1] * glScale)
        x2 = int(x + segs[i+1][0] * glScale)
        y2 = int(y + segs[i+1][1] * glScale)
        # Draw thickness by offsetting the line
        for dx in range(glThick):
            for dy in range(glThick):
                glTfft.draw_line(x1 + dx, y1 + dy, x2 + dx, y2 + dy, gColurNow)        
  
def drawLargeHHMM(sH1H2M1M2, x, y):
    #global glTfft,glScale,glSpacing,glColonSpacing
    global gPrevHHMM
    iCurrHHMM = int(sH1H2M1M2)
    sXorMask = digitXorCompare4(gPrevHHMM, iCurrHHMM)
    #print(f"{gPrevHHMM} {iCurrHHMM} => {sXorMask} ")
    if sXorMask[0] == '1':
        clear_digit(x, y)
        draw_digit(x, y, sH1H2M1M2[0]) # Draw H1
    x += glSpacing
    if sXorMask[1] == '1':
        clear_digit(x, y)
        draw_digit(x, y, sH1H2M1M2[1]) # Draw H2
    x += glColonSpacing # Wider space replaces colon
    if sXorMask[2] == '1':
        clear_digit(x, y)
        draw_digit(x, y, sH1H2M1M2[2]) # Draw M1
    x += glSpacing
    if sXorMask[3] == '1':
        clear_digit(x, y)
        draw_digit(x, y, sH1H2M1M2[3]) # Draw M2
    gPrevHHMM = iCurrHHMM

#---------------------------------    
# Seconds horizontal display
#---------------------------------
def init_seconds_bar():
    """
    Computes global layout values for the 60-dot seconds bar.
    Each dot is (2*radius+1) px wide, with a fixed gap between.
    Y=0 is top. Below larger HHMM is:
    gYdownTop10SecMarkerBar Marker bar 10 secs apart dots fixed then..
    gYdownSecondsBar seconds bar that fills left to right to mark a minute ending.
    """
    global gYdownSecondsBar, glSecXLeft, glSecDotRadius, glSecDotGap
    global glDigitHeight, glY, gYdownTop10SecMarkerBar, gYdownSecondsBar
    glSecDotRadius = 1       # Dot radius (1 → 3px diameter)
    glSecDotGap = 2          # Gap between dots
    # Row underneath the digits (increase to move further down)
    gYdownSecondsBar = glY + glDigitHeight + 30 # Y coordinate of seconds dots row
    # Each dot width = diameter + gap
    iDotWidth = (glSecDotRadius * 2 + 1) + glSecDotGap
    # Total width for 60 dots
    iTotalWidth = iDotWidth * 60
    # Center horizontally on 320px display
    glSecXLeft = (320 - iTotalWidth) // 2 # Left margin for centering
    
    #Below sets gYdownTop10SecMarkerBar so the 10-second markers are drawn
    #just above the dynamic seconds bar.
    # Place 10-second row 6 pixels above the seconds bar
    gYdownTop10SecMarkerBar = gYdownSecondsBar - 6
   
def drawTenSecMarkers():
    """
    Draw fixed blobs ten seconds apart
    Align vertically with the seconds bar dots.
    """
    global glSecXLeft, glSecDotRadius, glSecDotGap, glTfft, gYdownTop10SecMarkerBar
    # Width of each dot including gap
    iDotWidth = (glSecDotRadius * 2 + 1) + glSecDotGap
    # Draw markers at seconds as below...
    for iIdx in (0, 10, 20, 30, 40, 50, 60):
        # Find same X-center as the dynamic row
        iXCenter = glSecXLeft + iIdx * iDotWidth + glSecDotRadius
        # Draw filled dot
        for dx in range(-glSecDotRadius, glSecDotRadius + 1):
            for dy in range(-glSecDotRadius, glSecDotRadius + 1):
                glTfft.draw_pixel(iXCenter + dx, gYdownTop10SecMarkerBar + dy, gColurSecs)

giLastSecondDrawn = -1
def updateSecondsRow(iCurrentSecond):
    """
    Extend the seconds dot row.
    Clears only at start of a new minute.
    """
    global giLastSecondDrawn
    # ----- New minute detection -----
    if iCurrentSecond < giLastSecondDrawn:
        # Clear all dots ONCE
        drawTenSecMarkers() #As its colour can change
        for iSec in range(60):
            drawRowShwngSecnds(iSec, False)
        giLastSecondDrawn = -1
    # ----- Draw missing dots -----
    # Covers lost seconds during HH:MM redraw
    for iSec in range(giLastSecondDrawn + 1, iCurrentSecond + 1):
        drawRowShwngSecnds(iSec, True)
    giLastSecondDrawn = iCurrentSecond
 
def drawRowShwngSecnds(iSecond, bActive):
    """
    Draw a single dot for second iSecond at row gYdownSecondsBar.
    If bActive is True → bright dot, else erase to background.
    """
    global glSecXLeft, glSecDotRadius, glSecDotGap, glTfft
    # One dot width including gap
    iDotWidth = (glSecDotRadius * 2 + 1) + glSecDotGap
    # X coordinate for this second
    iXCenter = glSecXLeft + iSecond * iDotWidth + glSecDotRadius
    # Color: active = white, inactive = background black
    if bActive:
        iColor = gColurSecs #gColurRed default
    else:
        iColor = gColurBlack
    # Draw filled circle manually (simple square approximation)
    for dx in range(-glSecDotRadius, glSecDotRadius + 1):
        for dy in range(-glSecDotRadius, glSecDotRadius + 1):
            glTfft.draw_pixel(iXCenter + dx, gYdownSecondsBar + dy, iColor)

# ---- Main ----
async def main():
    global gcRegion
    initLCD()
    text2LCD(f"AMCLOK {VEERSION}") #Puts up welcome message

    #gDigitMinX, gDigitMinY, gDigitWidth, gDigitHeight = get_digit_bbox('8')
    #print(f"{gDigitMinX} {gDigitMinY}  {gDigitWidth} {gDigitHeight}")
    
    # -------------------------------
    # WiFi
    # -------------------------------
    gcRegion,ssid,sIPaddr = wifiConnect(fixed_ip="") # returns 'L' or 'P' or 'E' or None
    if gcRegion is None:
        text2LCD("No WiFi make EPLACE")
    if gcRegion == 'E':
        text2LCD([
        "In Fone Browser",
        f"open {sIPaddr}"
        ])
        start_config_portal()      
    else:    
        text2LCD(f"WiFi: {ssid}::{gcRegion}")
            
    # -------------------------------
    # Date/Time/DST setup
    # -------------------------------
    sTgudq = modDateTime.fnInitializeModule(gcRegion)
    print(sTgudq)

    initLCD() # Initialize LCD
    #init_digit_layout()
    init_seconds_bar() #Dynamic
    #drawTenSecMarkers() #Static header blobs every ten seconds
        
    # Start async background tasks
    asyncio.create_task(wdt_task())
    asyncio.create_task(time_display_task())
    asyncio.create_task(pirBacklightTask()) #NoteBL 3/3
    #In Thonny editor run below once to insert DST rule in flash. See modDateTime header
    #modDateTime.handleDstCommand("diUTC0;DST+1;M3.lastSun@01:00UTC-M10.lastSun@01:00UTC")
    while True:
        await asyncio.sleep(0.1)  # small sleep to yield control

# ---- Fail-safe run ----
try:
    asyncio.run(main())
except Exception as e:
    print("Fatal error, rebooting:", e)
    time.sleep(1)
    machine.reset()
#-----The End-----
