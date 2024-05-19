
# Distributed Image Processing App

A distributed image processing app that supports multiple requests at the same time.


## Features

- 5 image processing operations (Edge detection, Rotation, Blurring, Color Inversion, Grayscale)
- Multiple image uploads at once
- Ability to download images
- Ability to perform different operations on different images on a single upload
- Fault tolerant
- Easily Scalable
- Can support multiple clients communicating at the same time


## Installation

To run this application, have the Master Node code be on a virtual machine and each worker node be on different virtual machines and be sure to install the following on each machine running the following code on python 3.12

- For Client.py
```bash
pip install flask
pip install requests
```
- For MasterNode.py
```bash
pip install flask
pip install requests
pip install numpy
pip install azure-storage-queue
pip install azure-storage-blob
pip install paramiko
pip install opencv-python
```
- For WorkerNodes.py
```bash
pip install numpy
pip install azure-storage-queue
pip install azure-storage-blob
pip install paramiko
pip install opencv-python
```
- make sure that folders: templates and static are in the same directory as the Client.py
- Enable passwordless SSH connection between master node and all worker nodes
- Adjust the path to the WorkerNodes.py in the MasterNode.py and have all worker nodes have the same path to the WorkerNodes.py file
- Adjust private IP addresses and hostnames of worker nodes in the MasterNode.py
- Enable inbound and outbound communication on ports 8000 for HTTP and 9000 for UDP

## Demo
A demo where the project was used on Azure virtual machines
https://drive.google.com/file/d/1pMudHtt6M3dVVp1-2h7UeMoDoa8n8UZs/view?usp=drive_link

