import subprocess
import os

def run_command(namespace, command):
    output_dir = os.path.join("environments", namespace)
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "output.log")

    with open(output_path, "w") as out_file:
        full_command = f'cmd /c {command}' if os.name == 'nt' else command

        process = subprocess.Popen(
            full_command,
            shell=True,
            stdout=out_file,
            stderr=out_file
        )

    return process, output_path
