# -*- coding: utf-8 -*-
"""停止直播套装的全部后台服务"""
import base64, os, subprocess, sys

PS = r"""
$ProgressPreference = 'SilentlyContinue'
$pat = '标记服务|弹幕采集|主播引擎|抖音直连|winsound|弹幕转接'
$n = 0
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match $pat } |
  ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $n++ } catch {}
    Write-Output ("停止 " + $_.ProcessId)
  }
Write-Output ("共停止 " + $n + " 个进程")
"""

enc = base64.b64encode(PS.encode("utf-16-le")).decode()
subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc])
print()
print("服务已停止。OBS 和直播伴侣不受影响。")
