import subprocess
import os
import time
import math

CGROUP_ROOT = "/sys/fs/cgroup"
PROJECT_CGROUP_PARENT = os.path.join(CGROUP_ROOT, "exec_env")


def _sudo_sh(cmd: str):
    """
    Executa comando como root via sudo bash -lc "<cmd>".
    Usamos isso pra poder fazer redirecionamento (echo > arquivo)
    e mkdir dentro do mesmo shell rodando como root.
    """
    return subprocess.run(
        ["sudo", "bash", "-lc", cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _ensure_parent_cgroup():
    """
    Garante que /sys/fs/cgroup/exec_env existe e habilita cpu/memory
    tanto na raiz quanto no próprio /sys/fs/cgroup/exec_env, para que
    OS FILHOS (ex: /sys/fs/cgroup/exec_env/<namespace>) herdem
    cpu.max e memory.max.

    Passos equivalentes manualmente:
      sudo mkdir -p /sys/fs/cgroup/exec_env
      echo +cpu +memory > /sys/fs/cgroup/cgroup.subtree_control
      echo +cpu +memory > /sys/fs/cgroup/exec_env/cgroup.subtree_control
    """
    # cria o diretório pai (exec_env)
    _sudo_sh(f"mkdir -p {PROJECT_CGROUP_PARENT}")

    # habilita controladores no topo do cgroup v2
    _sudo_sh(f'echo +cpu +memory > {CGROUP_ROOT}/cgroup.subtree_control')

    # habilita controladores também no nível exec_env
    _sudo_sh(f'echo +cpu +memory > {PROJECT_CGROUP_PARENT}/cgroup.subtree_control')


def _snapshot_cgroup_limits(namespace: str, cpu_req: float, mem_req_mb: int):
    """
    Cria /sys/fs/cgroup/exec_env/<namespace> e grava limites equivalentes
    ao que passamos pro systemd-run:

      cpu.max      -> baseado em cpu_req (quantos "núcleos" lógicos o usuário pediu)
      memory.max   -> baseado em mem_req_mb (MB do slider)

    Importante:
    NÃO movemos o processo pra esse cgroup.
    Isso é só um espelho / auditoria visual.
    """

    # garante que exec_env existe e está com +cpu +memory liberado para filhos
    _ensure_parent_cgroup()

    ns_cgroup = os.path.join(PROJECT_CGROUP_PARENT, namespace)

    # cria diretório do namespace
    _sudo_sh(f"mkdir -p {ns_cgroup}")

    # agora que o pai já liberou "+cpu +memory" no subtree_control,
    # o filho deve ter arquivos cpu.max e memory.max disponíveis.

    # ----- cpu.max -----
    # Em cgroup v2:
    #   cpu.max = "<quota_us> <period_us>"
    # onde:
    #   quota_us  = quanto tempo de CPU você deixa usar por período
    #   period_us = janela (normalmente 100000us = 100ms)
    #
    # Se cpu_req = 1.0 núcleos -> quota ~= 100000
    # Se cpu_req = 2.0 núcleos -> quota ~= 200000
    period_us = 100000
    quota_us = int(math.floor(float(cpu_req) * period_us))
    if quota_us <= 0:
        quota_us = 1000  # evita 0 total

    _sudo_sh(f'echo "{quota_us} {period_us}" > {ns_cgroup}/cpu.max')

    # ----- memory.max -----
    mem_bytes = int(mem_req_mb) * 1024 * 1024
    _sudo_sh(f'echo "{mem_bytes}" > {ns_cgroup}/memory.max')


def run_command(namespace, command, cpu=1.0, memory=512):
    """
    1. Cria pasta environments/<namespace> e define output.log
    2. Sobe processo via systemd-run com limites reais:
         -p MemoryMax=...
         -p CPUQuota=...
    3. Captura o PID principal via systemctl show <unit>.MainPID
    4. Cria /sys/fs/cgroup/exec_env/<namespace> e escreve cpu.max/memory.max
       (espelho das configurações), sem mover o processo pra lá.
    """

    # pasta/arquivo de log
    output_dir = os.path.join("environments", namespace)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.abspath(os.path.join(output_dir, "output.log"))

    unit_name = f"env-{namespace}.service"

    # CPUQuota do systemd-run espera porcentagem
    # cpu=1.0   -> "100.0%"
    # cpu=0.3   -> "30.0%"
    # cpu=2.0   -> "200.0%"
    quota_pct = float(cpu) * 100.0
    quota_str = f"{quota_pct:.1f}%"  # exemplo "150.0%"

    cmd = [
        "sudo", "systemd-run", "--quiet",
        "--unit", unit_name,
        "--collect",
        "-p", f"MemoryMax={int(memory)}M",
        "-p", f"CPUQuota={quota_str}",
        "-p", "KillMode=mixed",
        "-p", "TimeoutStopSec=5s",
        "-p", f"StandardOutput=append:{output_path}",
        "-p", f"StandardError=append:{output_path}",
        "/bin/bash", "-lc", f"exec {command}"
    ]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # tenta capturar o MainPID atribuído pelo systemd-run
    main_pid = None
    for _ in range(20):  # ~2 segundos de tentativas
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

    # snapshot dos limites no cgroup "espelho"
    try:
        _snapshot_cgroup_limits(namespace, cpu_req=cpu, mem_req_mb=memory)
    except Exception as e:
        # se der erro (por ex, host em modo híbrido cgroup v1), não derruba o fluxo
        # print(f"[WARN] Falha cgroup snapshot: {e}")
        pass

    return unit_name, main_pid, output_path
