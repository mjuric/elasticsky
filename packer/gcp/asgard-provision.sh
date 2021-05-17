# install useful packages
sudo apt-get update
sudo apt-get install joe wget telnet dnsutils screen jq rsync -y

# provision the NFS server
# Based on:
#   https://help.ubuntu.com/community/SettingUpNFSHowTo
#   https://www.tecmint.com/install-nfs-server-on-centos-8/
sudo apt-get install nfs-kernel-server
sudo bash -c 'echo "/home      10.138.0.0/24(rw,async,root_squash,no_subtree_check)" >> /etc/exports'
sudo bash -c 'echo "/opt       10.138.0.0/24(rw,async,root_squash,no_subtree_check)" >> /etc/exports'
sudo exportfs -arv

#
# install central miniforge + mamba
#
wget https://github.com/conda-forge/miniforge/releases/download/4.10.1-0/Mambaforge-Linux-x86_64.sh
sudo bash Mambaforge-Linux-x86_64.sh -b -p /opt/conda
rm -f Mambaforge-Linux-x86_64.sh
sudo /opt/conda/bin/conda install mamba

# add conda to path system-wide
# FIXME: this should be sourced from /etc/bash.bashrc, otherwise conda isn't
# properly set up in non-login shells
sudo ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d

# create the 'ray' system account, so that google's guest tools don't auto-create it
# when ray adds an ssh key to the project
sudo useradd -r -m -d /var/lib/ray -s /bin/bash -G users ray

# useful timezone
sudo timedatectl set-timezone America/Los_Angeles

# build tools for ray, etc
# Adapted from https://docs.ray.io/en/master/development.html#building-ray-on-linux-macos-full
sudo apt-get update
sudo apt-get install -y build-essential curl unzip psmisc
sudo apt-get install -y npm

###############################################################################################
#
# Individual user bootstrap
#
###############################################################################################

#
# Build findorb. Unfortunately this has to be done on a per-user basis as
# findorb places configs into ~/.find_orb
#
sudo apt-get install g++ make libncurses5-dev -y

mkdir ~/tmp-build && cd ~/tmp-build
git clone https://github.com/Bill-Gray/find_orb.git
cd find_orb
bash DOWNLOAD.sh -d ..
bash INSTALL.sh -d .. -u
##sudo cp ~/bin/* /usr/local/bin
cd
rm -rf ~/tmp-build ~/include ~/lib
# add ~/bin to the PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc

#
# Set up an environment with Ray
#
. /opt/conda/etc/profile.d/conda.sh
conda create -n ray python=3.8
conda activate ray

conda install ray-core ray-autoscaler ray-dashboard --only-deps
pip install ray

#
# Set up a ray development environment
# Adapted from https://docs.ray.io/en/master/development.html#building-ray-on-linux-macos-full
#
conda create -n ray-devel python=3.8 mamba
conda activate ray-devel
conda install ray-core ray-autoscaler ray-dashboard --only-deps
mamba install cython
./ci/travis/install-bazel.sh
pushd dashboard/client/
npm install
npm run build
popd
cd python
pip install -e . --verbose 

###############################################################################################
#
# Individual user's laptop bootstrap
#
###############################################################################################
conda install google-cloud-sdk
gcloud config set project moeyens-thor-dev
gcloud auth application-default login
