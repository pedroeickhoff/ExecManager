class Environment:
    def __init__(self, namespace, cpu, memory, io, command):
        self.namespace = namespace
        self.cpu = int(cpu)
        self.memory = int(memory)
        self.io = int(io)
        self.command = command
        self.status = 'created'
        self.process = None     # mantido por compatibilidade, não usamos com systemd
        self.unit_name = None   # ex: env-<namespace>.service
        self.main_pid = None    # PID principal quando .service
