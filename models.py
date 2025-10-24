class Environment:
    def __init__(self, namespace, cpu, memory, io, command):
        self.namespace = namespace
        self.cpu = float(cpu)    
        self.memory = int(memory)
        self.io = int(io)
        self.command = command
        self.status = 'created'
        self.process = None     
        self.unit_name = None   
        self.main_pid = None    
