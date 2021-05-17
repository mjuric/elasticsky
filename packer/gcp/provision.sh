#!/bin/bash -ex

# Required and useful packages
sudo apt-get update
sudo apt-get install git joe jq rsync telnet screen -y

#
# Head Node:
# Hack to add authentication and dashboard proxying
#

sudo apt-get install nginx -y

sudo tee /etc/nginx/sites-available/default > /dev/null <<'EOF'
server {
	client_max_body_size 200M;

        listen 80 default_server;
        listen [::]:80 default_server;

        root /var/www/html;

        # Add index.php to the list if you are using PHP
        index index.html index.htm index.nginx-debian.html;

        server_name _;

	# proxy dashboard
        location / {
           # Make sure this points to the upstream server
           proxy_pass http://127.0.0.1:8265/;

           # See https://www.uvicorn.org/deployment/#running-behind-nginx
           proxy_set_header Host $http_host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_redirect off;
           proxy_buffering off;

           auth_basic           "Protected APIs";
           auth_basic_user_file /var/www/htpasswd;
        }

	# proxy API
        location /api/v1/ {
           # Make sure this points to the upstream server
           proxy_pass http://127.0.0.1:5000/api/v1/;

           # See https://www.uvicorn.org/deployment/#running-behind-nginx
           proxy_set_header Host $http_host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_redirect off;
           proxy_buffering off;

           auth_basic           "Protected APIs";
           auth_basic_user_file /var/www/htpasswd;
        }
}
EOF

sudo tee /var/www/htpasswd > /dev/null <<-'EOF'
	adam:$apr1$gWhgmDD/$AQ1uxV5SC/qnrARL95y5A.
EOF
sudo systemctl restart nginx

#
# Set up shared NFS filesystem mounts from Asgard
#
sudo apt-get install nfs-common -y
sudo ls -l /opt
sudo mkdir -p /adam /opt
sudo bash -c 'echo "nfs.api.b612.ai:/home	/home	nfs	defaults	0 0" >> /etc/fstab'
sudo bash -c 'echo "nfs.api.b612.ai:/opt	/opt	nfs	defaults	0 0" >> /etc/fstab'
sudo mount -a
sudo /opt/usersync.sh

#
# Set up the script to check for and create any new users
#
sudo apt-get install cron -y
sudo bash -c 'echo "* * * * * root test -e /opt/usersync.sh && /opt/usersync.sh 2>&1 | /usr/bin/logger -t USERSYNC" > /etc/cron.d/usersync'

#
# Create "ray" system user, whose $HOME is outside of /home
# and not shared amongst all instances.
#
sudo useradd -r -m -d /var/lib/ray -s /bin/bash -G users ray

#
# Add a backdoor for SSH access debugging
#
sudo useradd -r -m -d /var/lib/bd -s /bin/bash -G users bd
sudo -u bd bash -c 'mkdir ~/.ssh && chmod 700 ~/.ssh && echo "ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA3xX1xMZUPVZIEO/kAkHi8vECXYbNRbGgGhiDgFKIJRXsRBzBaauNQGEPHkY+MuqBnOWUg6msyXcPtTKmXSsnADrvi15Ujy5UARCIw8KscIvKNL4iLP/fVrmMgQB3Kr9UpVCwycFu/Bx8wwljtube0fOIZRFrxKV0wzOAsmYGzh2E2bUxvYvvWPCDJk3NoaOwnS0bKwzuP3aSxVNZPdm9X8Pyc7/eYullIG9HQk5MIsbfc5nypd8f83Kt2/s4D+TqkGeTc/KZHQa38J0CB0nQo4BzqTDelgiWEOyfrOBtIZ/tCAyLY4XnGl8/94kAneo58QkYVLeihYNc5IGdNSQRYQ== mjuric@caladan.astro.Princeton.EDU" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'

#
# Make all members of the 'users' group sudoers
# This lets us add Linux users who don't have an account on GCP
#
sudo bash -c 'echo "%users ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers.d/asgard_sudoers'
sudo chmod 0440 /etc/sudoers.d/asgard_sudoers

#
# Link remote conda to default bash environment
#
sudo ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d

#
# Useful timezone
#
sudo timedatectl set-timezone America/Los_Angeles

#
# Cleanup
#
(sudo dd if=/dev/zero of=/ZEROS bs=1M || /bin/true) && sudo rm -f /ZEROS
