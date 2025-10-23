Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/focal64"
  config.vm.hostname = "exec-env-vm"
  config.vm.network "private_network", ip: "192.168.56.10"

  # 🔁 Redireciona a porta 5000 da VM para o host
  config.vm.network "forwarded_port", guest: 5000, host: 5000

  config.vm.provider "virtualbox" do |vb|
    vb.name = "ExecEnvVM"
    vb.memory = 4096
    vb.cpus = 2
  end

  config.vm.provision "shell", inline: <<-SHELL
    apt-get update
    apt-get install -y apache2 python3 python3-pip cgroup-tools
    pip3 install flask flask-cors
    mkdir -p /var/www/html/exec_env_frontend
    chown -R vagrant:vagrant /var/www/html/exec_env_frontend
  SHELL
end
