#!/bin/bash

echo "hello"

sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get install docker.io -y
sudo apt-get install awscli -y

sudo usermod -aG docker $USER

sudo docker pull mjuric/elasticsky:latest
