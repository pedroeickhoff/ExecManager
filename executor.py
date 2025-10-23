import subprocess
import os

def run_command(namespace, command, cpu=1.0, memory=512):
    output_dir = os.path.join("environments", namespace)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "output.log")

    unit_name = f"env-{namespace}.scope"

    cmd = [
        "sudo", "systemd-run", "--quiet",
        "--unit", unit_name, "--scope",
        "-p", f"MemoryMax={int(memory)}M",
        "-p", f"CPUQuota={int(float(cpu) * 100)}%",
        "/bin/bash", "-lc", command
    ]

    with open(output_path, "w") as out_file:
        subprocess.Popen(cmd, stdout=out_file, stderr=out_file)

    try:
        mpid = subprocess.check_output(
            ["systemctl", "show", unit_name, "-p", "MainPID", "--value"]
        ).decode().strip()
        main_pid = int(mpid) if mpid and mpid != "0" else None
    except Exception:
        main_pid = None

    return unit_name, main_pid, output_path
