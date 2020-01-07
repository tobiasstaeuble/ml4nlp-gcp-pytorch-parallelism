# https://github.com/GoogleCloudPlatform/python-docs-samples/tree/master/compute/api

# python3 module requirements
# pip install google-api-python-client google-auth google-auth-httplib2

# create a service account as described here:
# https://cloud.google.com/docs/authentication/getting-started#auth-cloud-implicit-python

'''
The service account that runs this test must have the following roles:
- roles/compute.instanceAdmin.v1
- roles/compute.securityAdmin
- roles/iam.serviceAccountAdmin
- roles/iam.serviceAccountKeyAdmin
- roles/iam.serviceAccountUser
The Project Editor legacy role is not sufficient because it does not grant
several necessary permissions.
'''

# then create: 
# 1) a new project
# 2) a bucket (can be on coldline for testing)

import argparse
import os
import time
import requests
import random
import uuid
import subprocess
import base64
import json
import googleapiclient.discovery
from six.moves import input
from google.oauth2 import service_account

SERVICE_ACCOUNT_METADATA_URL = (
 'http://metadata.google.internal/computeMetadata/v1/instance/'
 'service-accounts/default/email')
HEADERS = {'Metadata-Flavor': 'Google'}


credentialFile        = 'service_account.json' # make sure this file is save, this is your private key
accountEmail          = '672443615215-compute@developer.gserviceaccount.com'
accountID             = 107454996668042976743
project               = 'ml4nlp'
projectName           = 'ml4nlp'
projectID             = 'ml4nlp'
projectNumber         = 672443615215
zone                  = 'us-central1-a'
bucket                = 'ml4nlp-bucket'
startupScript         = 'startup-script.sh'

PKFile                = None

# configure your machines here
machines = [
  {
    'name'  : 'ml4nlp-node-1',
    'gpu'   : True,
    'zone'  : 'us-central1-a'
  }, 
  {
    'name'  : 'ml4nlp-node-2',
    'gpu'   : True,
    'zone'  : 'us-east1-c'
  }
]

# if you have dedicated GPU quota >= x for one specific region, use same zone for x machines

def auth():
  # credentials = service_account.Credentials.from_service_account_file(credentialFile)
  os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(os.path.dirname(__file__), credentialFile)

def list_instances(compute, project):
  result = []
  for m in machines:
    tmp = compute.instances().list(project = project, zone = m['zone']).execute()
    if 'items' in tmp: 
      result.append(tmp)
  
  if len(result) == 0:
    return None
  return [r['items'] for r in result] if 'items' in result[0] else None

def create_fwrule(compute, project, zone, name):
  # firewall cofig to allow ssh connections
  firewall_config = {
    'name': name,
    'network': '/global/networks/default',
    'targetServiceAccounts': [
        accountEmail
    ],
    'sourceRanges': [
        '0.0.0.0/0'
    ],
    'allowed': [{
        'IPProtocol': 'tcp',
        'ports': [
            '22'
        ],
    }]
  }

  current = compute.firewalls().list(
    project=project).execute()

  if (current):
    if name in list([c['name'] for c in current['items']]):

      operation = compute.firewalls().delete(
        project=project,
        firewall=name).execute()
      wait_for_operation(compute, projectName, zone, operation['name'])

  compute.firewalls().insert(
      project=project,
      body=firewall_config).execute()

def create_instance(compute, project, zone, name, bucket):

  image_response = compute.images().getFromFamily(
    project = 'ubuntu-os-cloud', family='ubuntu-1604-lts').execute()
  source_disk_image = image_response['selfLink']

  # configuration of machine
  machine_type = "zones/%s/machineTypes/custom-2-8192" % zone
  startup_script = open(
    os.path.join(
      os.path.dirname(__file__), startupScript),'r').read()
  
  config = {
    'name': name,
    'machineType': machine_type,
    'disks': [
      {
        'boot': True,
        'autoDelete': True,
        'initializeParams': { 
          'sourceImage': source_disk_image,
          'diskSizeGb': '50'
        }
      }
    ],
    'guestAccelerators': [
      {
        'acceleratorCount': 1,
        'acceleratorType': 'projects/'+str(projectName)+'/zones/'+str(zone)+'/acceleratorTypes/nvidia-tesla-t4'
      }
    ],
    "scheduling": {
      "onHostMaintenance": "TERMINATE",  # required combination for GPU accelerated machines
    },
    'networkInterfaces': [
      {
        'network': 'global/networks/default',
        'accessConfigs': [
          {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
        ]
      }
    ],
    'serviceAccounts': [
      {
        'email': 'default',
        'scopes': [
          'https://www.googleapis.com/auth/devstorage.read_write',
          'https://www.googleapis.com/auth/logging.write'
        ]
      }
    ],
    'metadata': {
      'items': [
        {
          'key': 'startup-script',
          'value': 'startup_script'
        }, 
        {
          'key': 'bucket',
          'value': bucket
        },
        {
          'key': 'enable-oslogin',
          'value': 'TRUE'
        }
      ]
    }
  }

  return compute.instances().insert(
    project   = project,
    zone      = zone,
    body      = config).execute()
  
  

def delete_instance(compute, project, zone, name):
  return compute.instances().delete(
    project=project,
    zone=zone,
    instance=name).execute()
    

def wait_for_operation(compute, project, zone, operation):
  print('Waiting for operation to finish...')
  while True:
    result = compute.zoneOperations().get(
      project=project,
      zone=zone,
      operation=operation).execute()

    if result['status'] == 'DONE':
      print("done.")
      if 'error' in result:
        raise Exception(result['error'])
      return result
    time.sleep(1)

def default_spinup():
  auth()
  compute = googleapiclient.discovery.build('compute', 'v1')
  instances = list_instances(compute, projectName)

  create_fwrule(compute, projectName, zone, 'ml4nlp-fwrule')

  # delete old instances if spinup would result in a naming conflict
  if (instances):
    for instance in instances:
      if (instance[0]['name'] in [m['name'] for m in machines]):
        print("deleting instance %s" % instance[0]['name'])
        operation = delete_instance(compute, projectName, instance[0]['zone'].split('/')[-1], instance[0]['name'])
        wait_for_operation(compute, projectName, instance[0]['zone'].split('/')[-1], operation['name'])

  # create machines according to definition

  for machine in machines:
    print("creating instance %s" % machine['name'])
    operation = create_instance(compute, projectName, machine['zone'], machine['name'], bucket)
    wait_for_operation(compute, projectName, machine['zone'], operation['name'])

  # stop all instances // spindown.py?

  print('spinup finished.')

def default_teardown():
  auth()
  compute = googleapiclient.discovery.build('compute', 'v1')
  instances = list_instances(compute, projectName)

  # delete old instances
  if (instances):
    for instance in instances:
      if (instance[0]['name'] in [m['name'] for m in machines]):
        print("deleting instance %s" % instance[0]['name'])
        operation = delete_instance(compute, projectName, instance[0]['zone'].split('/')[-1], instance[0]['name'])
        wait_for_operation(compute, projectName, instance[0]['zone'].split('/')[-1], operation['name'])

def start_instances():
  auth()
  compute = googleapiclient.discovery.build('compute', 'v1')
  instances = list_instances(compute, projectName)

  for instance in instances:
    if (instance[0]['name'] in [m['name'] for m in machines]):
      if (instance[0]['status'] == 'TERMINATED'):
        operation = compute.instances().start(project=projectName, zone=instance[0]['zone'].split('/')[-1], instance=instance[0]['name']).execute()
        wait_for_operation(compute, projectName, instance[0]['zone'].split('/')[-1], operation['name'])
        
def stop_instances():
  auth()
  compute = googleapiclient.discovery.build('compute', 'v1')
  instances = list_instances(compute, projectName)

  for instance in instances:
    if (instance[0]['name'] in [m['name'] for m in machines]):
      if (instance[0]['status'] == 'RUNNING'):
        operation = compute.instances().stop(project=projectName, zone=instance[0]['zone'].split('/')[-1], instance=instance[0]['name']).execute()
        wait_for_operation(compute, projectName, instance[0]['zone'].split('/')[-1], operation['name'])
        
def get_ips(internal=False):
  auth()
  compute = googleapiclient.discovery.build('compute', 'v1')
  instances = list_instances(compute, projectName)

  ips = []

  for instance in instances:
    if (instance[0]['name'] in [m['name'] for m in machines]):
      if (instance[0]['status'] == 'RUNNING'):
        if (internal):
          ips.append(instance[0]['networkInterfaces'][0]['networkIP'])
        else:
          ips.append(instance[0]['networkInterfaces'][0]['accessConfigs'][0]['natIP'])

  return ips

def setup_resources():
  auth()
  compute = googleapiclient.discovery.build('compute', 'v1')
  instances = list_instances(compute, projectName)

  for instance in instances:

    # Grant the service account osLogin access on the test instance.
    compute.instances().setIamPolicy(
      project=project,
      zone=instance[0]['zone'].split('/')[-1],
      resource=instance[0]['id'],
      body={
        'bindings': [
          {
            'members': [
              'serviceAccount:' + accountEmail
            ],
            'role': 'roles/compute.osLogin'
          }
        ]
      }
    ).execute()

  for instance in instances:
    # Wait for the IAM policy to take effect.
    while compute.instances().getIamPolicy(
            project=project,
            zone=instance[0]['zone'].split('/')[-1],
            resource=instance[0]['id'],
            fields='bindings/role'
            ).execute()['bindings'][0]['role'] != 'roles/compute.osLogin':
      time.sleep(5)

# run a command on a remote system.
def run_ssh(ip, cmd, PKFile, wait=True):

  oslogin = googleapiclient.discovery.build('oslogin', 'v1')
  compute = googleapiclient.discovery.build('compute', 'v1')
  account = accountEmail
  hostname = ip

  if not account.startswith('users/'):
    account = 'users/' + account
  profile = oslogin.users().getLoginProfile(name=account).execute()
  username = profile.get('posixAccounts')[0].get('username')

  instances = list_instances(compute, projectName)

  ssh_command = [
    'ssh', '-i', PKFile, '-o', 'StrictHostKeyChecking=no',
    '{username}@{hostname}'.format(username=username, hostname=hostname),
    cmd,
  ]

  if (wait):
    ssh = subprocess.Popen(ssh_command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = ssh.stdout.readlines()
  else:
    ssh = subprocess.Popen(ssh_command, shell=False, stdin=None, stdout=None, stderr=None, close_fds=True)

  if (wait):
    return result if result else ssh.stderr.readlines()

  return None

def copy_file(ip, file, PKFile):
  print("copying file " + str(file) + " to " + str(ip) + "...")
  oslogin = googleapiclient.discovery.build('oslogin', 'v1')
  compute = googleapiclient.discovery.build('compute', 'v1')
  account = accountEmail
  hostname = ip

  if not account.startswith('users/'):
    account = 'users/' + account
  profile = oslogin.users().getLoginProfile(name=account).execute()
  username = profile.get('posixAccounts')[0].get('username')

  instances = list_instances(compute, projectName)

  ssh_command = [
    'scp', '-i', PKFile, '-o', 'StrictHostKeyChecking=no',
    file,
    '{username}@{hostname}:{destfile}'.format(username=username, hostname=hostname, destfile=file)
  ]

  ssh = subprocess.Popen(ssh_command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  result = ssh.stdout.readlines()
  print("copied file to " + str(ip) + ".")
  return result if result else ssh.stderr.readlines()

def create_ssh_key(expire_time=300):

  account = accountEmail
  if not account.startswith('users/'):
    account = 'users/' + account

  oslogin = googleapiclient.discovery.build('oslogin', 'v1')

  """Generate an SSH key pair and apply it to the specified account."""
  private_key_file = '/tmp/key-' + str(uuid.uuid4())
  execute(['ssh-keygen', '-t', 'rsa', '-N', '', '-f', private_key_file])

  with open(private_key_file + '.pub', 'r') as original:
      public_key = original.read().strip()

  # Expiration time is in microseconds.
  expiration = int((time.time() + expire_time) * 1000000)
  body = {
      'key': public_key,
      'expirationTimeUsec': expiration,
  }

  oslogin.users().importSshPublicKey(parent=account, body=body).execute()
  return private_key_file

# execute a local command
def execute(cmd, cwd=None, capture_output=False, env=None, raise_errors=True):
  """Execute an external command (wrapper for Python subprocess)."""
  stdout = subprocess.PIPE if capture_output else None
  process = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=stdout)
  output = process.communicate()[0]
  returncode = process.returncode
  if returncode:
    # Error
    if raise_errors:
      raise subprocess.CalledProcessError(returncode, cmd)
    else:
      pass
  if output:
    print(output)
  return returncode, output

