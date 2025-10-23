import subprocess
import os

def run_command(namespace, command, cpu=1.0, memory=512):
    # Cria diretório de output
    output_dir = os.path.join("environments", namespace)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "output.log")

    # Monta o comando com limites reais usando systemd-run
    # --quiet remove a mensagem "Running scope as unit..."
    # sudo é necessário para evitar erro de permissão
    systemd_cmd = (
        f"sudo systemd-run --quiet --scope "
        f"-p MemoryMax={memory}M "
        f"-p CPUQuota={int(cpu * 100)}% "
        f"{command}"
    )

    # Executa o comando e redireciona saída para o log
    with open(output_path, "w") as out_file:
        process = subprocess.Popen(
            systemd_cmd,
            shell=True,
            stdout=out_file,
            stderr=out_file
        )

    return process, output_path
