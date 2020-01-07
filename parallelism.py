import os
import time
import random
import base64
import json
import googleapiclient.discovery
from google.oauth2 import service_account


# the manager can create / destroy / start / stop VMs
import manager

# create a new key file or use an existing one
# manager.create_ssh_key can create a pair and associate the public key with the service POSIX account (sa_*)
keyfile = None                  # 'your_key.file'
script = "parallel_torch.py"    # script that implements DDP
prepMachines = False             # set to true if these are new machines

# spinup / teardown / startup
#manager.default_spinup()
manager.start_instances()

# gather IPs of running instances and setup resources
ips = manager.get_ips()
manager.setup_resources()

# as mentioned above
if (keyfile == None):
  PKFile = manager.create_ssh_key()
else:
  PKFile = keyfile

#print("waiting some time for machine startup to complete...")
#time.sleep(120)

for ip in ips:
  cmd = 'uname -a'
  print("running connection tests...")
  print(manager.run_ssh(ip, cmd, PKFile))

if (prepMachines):
  for ip in ips:
    print("installing pip and pytorch...")
    cmd = 'sudo apt-get update'
    manager.run_ssh(ip, cmd, PKFile)
    cmd = 'sudo apt-get install --yes python3-pip'
    print(manager.run_ssh(ip, cmd, PKFile))
    cmd = 'umask 022 | sudo pip3 install torch'
    print(manager.run_ssh(ip, cmd, PKFile))

    print("installing gpu drivers...")
    # family = ubuntu 16.04, therefore use these drivers
    cmd = 'curl -O http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64/cuda-repo-ubuntu1604_10.0.130-1_amd64.deb'
    manager.run_ssh(ip, cmd, PKFile)
    cmd = 'sudo dpkg -i cuda-repo-ubuntu1604_10.0.130-1_amd64.deb'
    manager.run_ssh(ip, cmd, PKFile)
    cmd = 'sudo apt-key adv --fetch-keys http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64/7fa2af80.pub'
    manager.run_ssh(ip, cmd, PKFile)
    cmd = 'sudo apt-get update'
    manager.run_ssh(ip, cmd, PKFile)
    cmd = 'sudo apt-get install cuda --yes'
    print(manager.run_ssh(ip, cmd, PKFile))

  print("waiting some time for machine to restart")
  time.sleep(120)

# get internal ips (non-NATed)
internalIPs = manager.get_ips(internal=True)

rank = 0
for ip in ips:
  print(manager.copy_file(ip, script, PKFile))
  cmd = 'python3 parallel_torch.py --worldsize=2 --rank=' + str(rank) + ' --master=' + internalIPs[0] + ':54321'
  print(manager.run_ssh(ip, cmd, PKFile, False))
  rank += 1
# run a command


