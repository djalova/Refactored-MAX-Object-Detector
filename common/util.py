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

import inspect
import os
import textwrap
import urllib.request

# Local imports
import common.prepost as prepost
import common.inference_request as inference_request

def fetch_or_use_cached(temp_dir, file_name, url):
  # type: (str, str, str) -> str
  """
  Check for a cached copy of the indicated file in our temp directory.

  If a copy doesn't exist, download the file.

  Arg:
    temp_dir: Local temporary dir
    file_name: Name of the file within the temp dir, not including the temp
      dir path
    url: Full URL from which to download the file, including remote file
      name, which can be different from file_name

  Returns the path of the cached file.
  """
  cached_filename = "{}/{}".format(temp_dir, file_name)
  if not os.path.exists(cached_filename):
    print("Downloading {} to {}".format(url, cached_filename))
    urllib.request.urlretrieve(url, cached_filename)
  return cached_filename


_BEGIN_MARKER = "# BEGIN MARKER FOR CODE GENERATOR"
_END_MARKER = "# END MARKER FOR CODE GENERATOR"
_INDENT_TO_ADD = "  "
def _retrieve_code_snippet(module_ref):
  # type: (Any) -> str
  """
  Subroutine of generate_wml_function() retrieving marked code snippets from
  Python source files.

  Args:
    module_ref: Reference to module containing the code snippet to grab
  """
  file_name = inspect.getfile(module_ref)
  with open(file_name) as f:
    lines = f.readlines()
    begin, end = -1, -1
    for i in range(len(lines)):
      if _BEGIN_MARKER in lines[i] and begin == -1:
        begin = i + 1
      elif _END_MARKER in lines[i]:
        end = i
  if begin == -1:
    raise ValueError("Didn't find begin marker in source file {} for module "
                     "{}".format(file_name, module_ref))
  if end == -1:
    raise ValueError("Didn't find end marker in source file {} for module "
                     "{}".format(file_name, module_ref))
  snippet = "".join(lines[begin:end])
  # Fix indent to match generated outer function
  return textwrap.indent(snippet, _INDENT_TO_ADD)


def generate_wml_function(handlers_ref):
  # type: (Any) -> str
  """
  Generate and return a deployable WML function that wraps a set of handlers.

  Args:
    handlers_ref: Reference to an class type (NOT an instance) of the handlers
    class -- for example, handlers.ObjectDetectorHandlers. This class must be a
    subclass of
    `PrePost`
  """
  # WML deployable functions need to be Python closures, and Python is
  # conservative about what gets captured in a closure. Auxiliary classes
  # either need to be importable on the remote machine or defined in the
  # function that creates the closure. For the time being, we cat everything we
  # need into the function. Eventually this approach should be replaced with
  # a pip install/import of the relevant framework classes.
  _FUNCTION_TEMPLATE = """
def deployable_funtion():
{prepost_class_def}
{inference_request_class_def}
{handlers_class_def}
  
  def score(function_payload):
    # TODO: Turn function_payload into a request
    h = {handlers_class_name}()
    h.pre_process(request)
    # TODO: Invoke WML deployed model
    h.post_process(request)
    return request.processed_outputs
    
  return score
"""

  # Use reflection to find the class source files so that we don't have to
  # hard-code their relative locations here
  params_dict = {
    "prepost_class_def" : _retrieve_code_snippet(prepost),
    "inference_request_class_def" : _retrieve_code_snippet(inference_request),
    "handlers_class_def" : _retrieve_code_snippet(handlers_ref),
    "handlers_class_name" : handlers_ref.__name__
  }

  generated_code = _FUNCTION_TEMPLATE.format(**params_dict)
  return generated_code