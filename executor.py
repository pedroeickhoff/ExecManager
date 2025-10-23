import subprocess
import os
import time

def run_command(namespace, command, cpu=1.0, memory=512):
    """
    Inicia o comando em um .service transitório (systemd-run) com limites reais.
    Retorna (unit_name, main_pid, output_path).
    """
    output_dir = os.path.join("environments", namespace)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "output.log")

    unit_name = f"env-{namespace}.service"

    cmd = [
        "sudo", "systemd-run", "--quiet",
        "--unit", unit_name,
        "--collect",                      # limpa a unit ao terminar
        "-p", f"MemoryMax={int(memory)}M",
        "-p", f"CPUQuota={int(float(cpu) * 100)}%",
        "-p", "KillMode=mixed",           # mata processo e filhos
        "-p", "TimeoutStopSec=5s",
        "/bin/bash", "-lc", f"exec {command}"  # 'exec' torna o processo alvo o MainPID
    ]

    # Dispara e grava os logs do systemd-run no output.log
    with open(output_path, "w") as out_file:
        subprocess.Popen(cmd, stdout=out_file, stderr=out_file)

    # MainPID pode demorar um pouco; faz polling curto
    main_pid = None
    for _ in range(15):  # ~1.5s
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
