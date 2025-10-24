# Vagrantfile
Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/focal64"
  config.vm.hostname = "exec-env-vm"

  # Rede
  config.vm.network "private_network", ip: "192.168.56.10"
  config.vm.network "forwarded_port", guest: 5000, host: 5000, auto_correct: true

  # Recursos
  config.vm.provider "virtualbox" do |vb|
    #vb.name = "ExecEnvVM"
    vb.memory = 4096
    vb.cpus = 2
  end

  # Provisionamento
  config.vm.provision "shell", inline: <<-SHELL
    set -eux

    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      apache2 python3 python3-pip \
      mariadb-server mariadb-client

    # Pacotes Python usados no app
    pip3 install --no-cache-dir flask flask-cors psutil PyMySQL

    # Configura MariaDB (MySQL) e schema
    systemctl enable --now mariadb

    # Cria DB, usuário e tabelas (idempotente)
    mysql -uroot <<'SQL'
CREATE DATABASE IF NOT EXISTS execenv CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'execenv'@'%' IDENTIFIED BY 'execenvpwd';
GRANT ALL PRIVILEGES ON execenv.* TO 'execenv'@'%';
FLUSH PRIVILEGES;

USE execenv;

CREATE TABLE IF NOT EXISTS environments (
  namespace     VARCHAR(255) PRIMARY KEY,
  command       TEXT,
  cpu           FLOAT,
  memory        INT,
  io            INT,
  unit_name     VARCHAR(255),
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_status   VARCHAR(32),
  last_pid      INT,
  process_name  VARCHAR(255)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS env_metrics (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  namespace     VARCHAR(255) NOT NULL,
  ts            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  status        VARCHAR(32),
  cpu_pct       FLOAT,
  rss_mb        INT,
  io_read       BIGINT,
  io_write      BIGINT,
  pid           INT,
  INDEX idx_ns_ts (namespace, ts)
) ENGINE=InnoDB;
SQL

    # Permitir que o usuário 'vagrant' chame systemctl/systemd-run sem senha
    echo "vagrant ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /usr/bin/systemd-run" >/etc/sudoers.d/execenv
    chmod 440 /etc/sudoers.d/execenv

    # --- Frontend (Apache) ---
    mkdir -p /var/www/html/exec_env_frontend
    cp -f /vagrant/index.html /var/www/html/exec_env_frontend/ || true
    cp -f /vagrant/style.css  /var/www/html/exec_env_frontend/ || true
    cp -f /vagrant/script.js  /var/www/html/exec_env_frontend/ || true
    chown -R www-data:www-data /var/www/html/exec_env_frontend
    systemctl enable --now apache2

    # --- Service do Flask (backend) ---
    cat >/etc/systemd/system/execenv.service <<'UNIT'
    [Unit]
    Description=ExecEnv Flask API
    After=network.target mariadb.service

    [Service]
    Type=simple
    WorkingDirectory=/vagrant
    ExecStart=/usr/bin/python3 /vagrant/app.py
    Environment=PYTHONUNBUFFERED=1
    Restart=on-failure
    User=vagrant
    Group=vagrant

    [Install]
    WantedBy=multi-user.target
    UNIT

    systemctl daemon-reload
    systemctl enable --now execenv.service

    # Feedback rápido
    systemctl --no-pager status execenv.service || true
    echo "Frontend:  http://192.168.56.10/exec_env_frontend/"
    echo "API:       http://192.168.56.10:5000/"
  SHELL
end
