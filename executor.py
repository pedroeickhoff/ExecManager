import subprocess
import os
import time

def run_command(namespace, command, cpu=1.0, memory=512):
  
    output_dir = os.path.join("environments", namespace)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.abspath(os.path.join(output_dir, "output.log"))

    unit_name = f"env-{namespace}.service"

    quota_pct = float(cpu) * 100.0
    quota_str = f"{quota_pct:.1f}%"  

    cmd = [
        "sudo", "systemd-run", "--quiet",
        "--unit", unit_name,
        "-p", f"MemoryMax={int(memory)}M",
        "-p", f"CPUQuota={quota_str}",
        "-p", "KillMode=mixed",
        "-p", "TimeoutStopSec=5s",
        "-p", f"StandardOutput=append:{output_path}",
        "-p", f"StandardError=append:{output_path}",
        "/bin/bash", "-lc", f"exec {command}"
    ]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    main_pid = None
    for _ in range(20):  
        try:
            mpid = subprocess.check_output(
                ["systemctl", "show", unit_name, "-p", "MainPID", "--value"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if mpid and mpid != "0":
                main_pid = int(mpid)
                break
        except Exception:
            pass
        time.sleep(0.1)

    return unit_name, main_pid, output_path
