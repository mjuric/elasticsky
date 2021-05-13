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
# Dev quality-of-life:
# Mount shared NFS filesystem to /adam
#
sudo apt-get install nfs-common -y
mkdir /adam
echo "nfs.api.b612.ai:/adam	/adam	nfs	defaults	0 0" >> /etc/fstab
mount -a

#
# Dev quality-of-life:
# Mirror the users from /
# FIXME: there's got to be a better way to do this w. Google's tools (OS Login?)
#

#
# Build findorb
#
sudo apt-get install g++ make libncurses5-dev -y

mkdir ~/software && cd ~/software
git clone https://github.com/Bill-Gray/find_orb.git
cd find_orb
/bin/bash DOWNLOAD.sh -d ..
/bin/bash INSTALL.sh -d .. -u
sudo cp ~/bin/* /usr/local/bin
cd
rm -rf ~/software

sudo apt-get remove g++ make libncurses5-dev -y
sudo apt autoremove -y

#
# Set up Mambaforge
#
wget https://github.com/conda-forge/miniforge/releases/download/4.10.1-0/Mambaforge-Linux-x86_64.sh
bash Mambaforge-Linux-x86_64.sh -b
rm -f Mambaforge-Linux-x86_64.sh
./mambaforge/bin/conda init
export PATH="$HOME/mambaforge/bin:$PATH"

#
# Install ray
#
# Downgrade Python to 3.8 as ray doesn't speak 3.9 yet
mamba install python=3.8 -y
mamba install ray-core ray-autoscaler ray-dashboard --only-deps -y
pip install ray

#
# Install elasticsky prerequisites
#
mamba install pandas tabulate uvicorn fastapi python-multipart passlib aiofiles -y


#
# Cleanup
#
conda clean --all -y

(sudo dd if=/dev/zero of=/ZEROS bs=1M || /bin/true) && sudo rm -f /ZEROS

