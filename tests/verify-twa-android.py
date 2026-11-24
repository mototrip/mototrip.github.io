import json, re, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path

out=Path("twa-emulator-results")
out.mkdir(exist_ok=True)
pkg="com.mototrip.app.twa"
apk="trip/android-app/app/build/outputs/apk/release/app-release.apk"

def adb(*a,check=True):
    p=subprocess.run(["adb",*map(str,a)],capture_output=True,timeout=75)
    if check and p.returncode: raise RuntimeError("adb "+str(a)+": "+p.stderr.decode(errors="replace")[-500:])
    return p
def snap(name):
    p=adb("exec-out","screencap","-p")
    assert p.stdout.startswith(b"\x89PNG\r\n\x1a\n")
    (out/(name+".png")).write_bytes(p.stdout)
def ui(name):
    adb("shell","uiautomator","dump","/sdcard/twa-ui.xml",check=False)
    raw=adb("exec-out","cat","/sdcard/twa-ui.xml",check=False).stdout
    (out/(name+".xml")).write_bytes(raw)
    nodes=[]
    try:
        for e in ET.fromstring(raw).iter("node"):
            t=e.attrib.get("text",""); d=e.attrib.get("content-desc","")
            if t or d: nodes.append({"text":t,"desc":d,"bounds":e.attrib.get("bounds","")})
    except ET.ParseError: pass
    (out/(name+".json")).write_text(json.dumps(nodes,indent=2,ensure_ascii=False))
    print("EMULATOR_VISIBLE="+str([x["text"] or x["desc"] for x in nodes][:32]),flush=True)
    return nodes
def tap(nodes,needle):
    for n in nodes:
        if re.search(needle,n["text"]+" "+n["desc"],re.I):
            m=re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",n["bounds"])
            if m:
                a,b,c,d=map(int,m.groups())
                adb("shell","input","tap",(a+c)//2,(b+d)//2)
                return True
    return False
def log():
    s=adb("logcat","-d","-v","time",check=False).stdout.decode(errors="replace")
    (out/"android-logcat.txt").write_text(s[-250000:])
    errs=[x for x in re.findall(r"FATAL EXCEPTION:[\s\S]{0,2400}",s) if pkg in x]
    (out/"mototrip-fatal-crashes.txt").write_text("\n\n".join(errs))
    return errs

try:
    assert Path(apk).is_file()
    assert adb("shell","getprop","ro.build.version.sdk").stdout.strip()==b"35"
    print("PIXEL_7_EMULATOR_API35=PASS",flush=True)
    adb("install","-r",apk)
    assert pkg.encode() in adb("shell","pm","list","packages",pkg).stdout
    print("SIGNED_RELEASE_APK_INSTALL=PASS",flush=True)
    adb("logcat","-c",check=False)
    adb("shell","am","start","-n",pkg+"/com.mototrip.app.MainActivity")
    time.sleep(14)
    nodes=ui("01-android-first-launch")
    snap("01-android-first-launch")
    for i in range(9):
        text=" ".join((n["text"]+" "+n["desc"]) for n in nodes).lower()
        if "welcome to mototrip" in text and "continue as guest" in text: break
        if "welcome to chrome" in text or "sign in to chrome" in text:
            if tap(nodes,r"use without an account|no thanks|skip|not now"):
                time.sleep(7); nodes=ui("chrome-setup"); continue
        time.sleep(5); nodes=ui("poll-"+str(i))
    snap("02-mototrip-welcome")
    names=[(n["text"] or n["desc"]).strip() for n in nodes]
    assert any("Welcome to MotoTrip" in n for n in names), "MotoTrip screen not loaded"
    print("MOTOTRIP_WELCOME_SCREEN=PASS",flush=True)
    browser_bar=["Close tab","Connection is secure","Customize and control Google Chrome","Web View","mototrip.github.io"]
    bad=[item for item in browser_bar if item.casefold() in [n.casefold() for n in names]]
    if bad:
        print("UNVERIFIED_CHROME_BAR="+repr(bad),flush=True)
        raise AssertionError("Chrome browser URL toolbar still visible")
    print("FULLSCREEN_NO_CHROME_URL_BAR=PASS",flush=True)
    if tap(nodes,r"Continue as Guest"):
        time.sleep(4)
        profile=ui("03-guest-profile"); snap("03-guest-profile")
        assert any("My Rider Profile" in (n["text"]+" "+n["desc"]) for n in profile)
        print("GUEST_PROFILE=PASS",flush=True)
    assert not log(),"MotoTrip fatal crash"
    print("MOTOTRIP_CRASHES=0",flush=True)
    print("SIGNED_TWA_FULLSCREEN_TEST=PASS",flush=True)
except Exception as e:
    print("SIGNED_TWA_FULLSCREEN_TEST=FAIL "+str(e),file=sys.stderr,flush=True)
    try: snap("failure");ui("failure");log()
    except Exception: pass
    sys.exit(1)
