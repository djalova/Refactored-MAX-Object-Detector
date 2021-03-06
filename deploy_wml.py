# Coypright 2019 IBM. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from typing import Dict

# Local imports
import common.util as util
import common.inference_request as inference_request
import handlers

# IBM Cloud imports
import ibm_boto3
import ibm_boto3.s3.transfer
from ibm_botocore.client import Config
from ibm_botocore.exceptions import ClientError

from watson_machine_learning_client import WatsonMachineLearningAPIClient

# Uncomment to enable tracing of object storage REST calls.
# ibm_boto3.set_stream_logger('')

# Leftover from an attempt to enable further logging. Didn't seem to work
# back then.
# from ibm_botocore import history
# history.get_global_history_recorder().enable()


# System imports
import os
import json
import subprocess
import sys

################################################################################
# CONSTANTS

# Authorization endpoint used in the example code at
# https://console.bluemix.net/docs/services/cloud-object-storage/libraries/
# python.html#client-credentials
# This may or may not be the only endpoint. This may or not work with all
# object storage instances.
_COS_AUTH_ENDPOINT = "https://iam.cloud.ibm.com/oidc/token"

# Name of the object storage bucket we use to hold the "input" to the
# dummy "training script"
_INPUT_BUCKET = "max-input-bucket"

_SAVED_MODEL_DIR = "./saved_model"
_SAVED_MODEL_TARBALL = _SAVED_MODEL_DIR + ".tar.gz"
_SAVED_MODEL_TARBALL_PATH_IN_COS = "saved_model.tar.gz"

_PREPOST_FUNC_FILE = "pre_post.py"

# Preshrunk configuration object handle for ibm_boto3 block transfers
_ONE_MEGABYTE = 1024 * 1024
_COS_TRANSFER_BLOCK_SIZE = 16 * _ONE_MEGABYTE
_COS_TRANSFER_MULTIPART_THRESHOLD = 128 * _ONE_MEGABYTE
_COS_TRANSFER_CONFIG_OBJECT = ibm_boto3.s3.transfer.TransferConfig(
  multipart_threshold=_COS_TRANSFER_MULTIPART_THRESHOLD,
  multipart_chunksize=_COS_TRANSFER_BLOCK_SIZE
)

# Various metadata fields that you need to pass to the WML service when
# deploying a model.
_WML_META_AUTHOR_NAME = "CODAIT"
_WML_META_NAME = "MAX Object Detector"
_WML_META_DESCRIPTION = "Test MAX Models"
_WML_META_FRAMEWORK_NAME = "tensorflow"
_WML_META_FRAMEWORK_VERSION = "1.11"
_WML_META_RUNTIME_NAME = "python"
_WML_META_RUNTIME_VERSION = "3.6"
#_WML_META_FRAMEWORK_LIBRARIES = [{'name':'keras', 'version': '2.1.3'}]


################################################################################
# SUBROUTINES


################################################################################
# BEGIN SCRIPT
def main():
  """
  Script to deploy this model to Watson Machine Learning.

  Before running this script, you must perform the following manual steps:
  * Create a file `ibm_cloud_credentials.json` in this directory, if such a
    file doesn't already exist.
    Initialize the file with an empty JSON record, i.e. "{ }".
  * Create a Watson Machine Learning (WML) instance.
  * Navigate to your WML instance's web UI and click on the "Service
    credentials" link, then click on "New credential" to create a new set of
    service credentials. Copy the credentials into `ibm_cloud_credentials.json`
    under the key "WML_credentials".
  """
  # STEP 1: Read IBM Cloud authentication data from the user's local JSON
  # file.
  with open("./ibm_cloud_credentials.json") as f:
    creds_json = json.load(f)

  print("creds_json is:\n{}".format(creds_json))

  _WML_CREDENTIALS = creds_json["WML_credentials"]

  # STEP 2: Convert the SavedModel directory to a tarball. WML expects a
  # tarball.
  if os.path.exists(_SAVED_MODEL_TARBALL):
    os.remove(_SAVED_MODEL_TARBALL)
  subprocess.run(["tar", "--create", "--gzip", "--verbose",
                  "--directory={}".format(_SAVED_MODEL_DIR),
                  "--file={}".format(_SAVED_MODEL_TARBALL),
                  "saved_model.pb"])

  # STEP 3: Open a connection to the WML Python API.
  client = WatsonMachineLearningAPIClient(_WML_CREDENTIALS)

  # STEP 4: Set up the metadata fields that WML requires in every model and
  # can't read out of the SavedModel files.
  # The keys that you need in your JSON structure are accessible only via an
  # object that you can only create after creating a connection.
  model_metadata = {
    client.repository.ModelMetaNames.AUTHOR_NAME: _WML_META_AUTHOR_NAME,
    client.repository.ModelMetaNames.NAME: _WML_META_NAME,
    client.repository.ModelMetaNames.DESCRIPTION: _WML_META_DESCRIPTION,
    client.repository.ModelMetaNames.FRAMEWORK_NAME: _WML_META_FRAMEWORK_NAME,
    client.repository.ModelMetaNames.FRAMEWORK_VERSION:
      _WML_META_FRAMEWORK_VERSION,
    client.repository.ModelMetaNames.RUNTIME_NAME: _WML_META_RUNTIME_NAME,
    client.repository.ModelMetaNames.RUNTIME_VERSION: _WML_META_RUNTIME_VERSION,
    # client.repository.ModelMetaNames.FRAMEWORK_LIBRARIES:
    #   _WML_META_FRAMEWORK_LIBRARIES
  }
  print("Model metadata: {}".format(model_metadata))

  # STEP 5: Use a little-known API to upload the SavedModel tarball and
  # associate our model metadata with it.
  model_details = client.repository.store_model(
    model=_SAVED_MODEL_TARBALL,
    meta_props=model_metadata)
  print("Model details: {}".format(model_details))

  # STEP 6: Deploy the model the you just uploaded to the model repository
  deployment_details = client.deployments.create(
    model_details['metadata']['guid'],
    name=model_details['entity']['name'])
  print("Deployment details: {}".format(deployment_details))

  deployment_url = client.deployments.get_scoring_url(deployment_details)
  print("Deployment URL: {}".format(deployment_url))

  # STEP 7: Generate a deployable function to cover pre- and post-processing
  # operations.
  func_body = util.generate_wml_function(handlers.ObjectDetectorHandlers,
                                         _WML_CREDENTIALS, deployment_url)
  with open("deployable_function.py", "w") as f:
    f.write(func_body)

  # STEP 8: Deploy the deployable function to WML
  import deployable_function
  meta_data = {client.repository.FunctionMetaNames.NAME:
               'MAX Object Detector Pre/Post-Processing'}
  function_details = client.repository.store_function(
    meta_props=meta_data, function=deployable_function.deployable_function)
  print("Function details: {}".format(function_details))

  function_deployment_details = client.deployments.create(
    artifact_uid=function_details["metadata"]["guid"],
    name='MAX Object Detector Pre/Post-Processing Deployment')
  print("Function deployment details: {}".format(function_deployment_details))

  function_deployment_endpoint_url = client.deployments.get_scoring_url(
    function_deployment_details)
  print("Function deployment URL: {}".format(function_deployment_endpoint_url))

  print('Lines to add to ibm_cloud_credentials.json:\n'
        '    "WML_model_ID": "{}",\n'
        '    "WML_deployment_ID": "{}",\n'
        '    "WML_function_url": "{}"'
        ''.format(model_details["metadata"]["guid"],
                  deployment_details["metadata"]["guid"],
                  function_deployment_endpoint_url))

  print("Done.")


if __name__ == "__main__":
  main()
