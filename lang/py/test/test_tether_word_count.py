#!/usr/bin/env python

##
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import, division, print_function

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import avro
import avro.datafile
import avro.io
import avro.schema
import avro.tether.tether_task_runner
import set_avro_test_path

_IN_SCHEMA = '"string"'

# The schema for the output of the mapper and reducer
_OUT_SCHEMA = """{
  "type": "record",
  "name": "Pair",
  "namespace": "org.apache.avro.mapred",
  "fields": [{"name": "key", "type": "string"},
             {"name": "value", "type": "long", "order": "ignore"}]
}"""


class TestTetherWordCount(unittest.TestCase):
  """unittest for a python tethered map-reduce job."""

  def _write_lines(self,lines,fname):
    """
    Write the lines to an avro file named fname

    Parameters
    --------------------------------------------------------
    lines - list of strings to write
    fname - the name of the file to write to.
    """
    #recursively make all directories
    dparts=fname.split(os.sep)[:-1]
    for i in range(len(dparts)):
      pdir=os.sep+os.sep.join(dparts[:i+1])
      if not(os.path.exists(pdir)):
        os.mkdir(pdir)

    datum_writer = avro.io.DatumWriter(_IN_SCHEMA)
    writers_schema = avro.schema.parse(_IN_SCHEMA)
    with avro.datafile.DataFileWriter(open(fname, 'wb'), datum_writer, writers_schema) as writer:
      for datum in lines:
        writer.append(datum)

  def _count_words(self,lines):
    """Return a dictionary counting the words in lines
    """
    counts={}

    for line in lines:
      words=line.split()

      for w in words:
        if not(w.strip() in counts):
          counts[w.strip()]=0

        counts[w.strip()]=counts[w.strip()]+1

    return counts

  def test1(self):
    """
    Run a tethered map-reduce job.

    Assumptions: 1) bash is available in /bin/bash
    """
    proc=None
    exfile = None

    try:
      # TODO we use the tempfile module to generate random names
      # for the files
      base_dir = "/tmp/test_tether_word_count"
      if os.path.exists(base_dir):
        shutil.rmtree(base_dir)

      inpath = os.path.join(base_dir, "in")
      infile=os.path.join(inpath, "lines.avro")
      lines=["the quick brown fox jumps over the lazy dog",
             "the cow jumps over the moon",
             "the rain in spain falls mainly on the plains"]

      self._write_lines(lines,infile)

      true_counts=self._count_words(lines)

      if not(os.path.exists(infile)):
        self.fail("Missing the input file {0}".format(infile))

      # write the schema to a temporary file
      with tempfile.NamedTemporaryFile(mode='wb',
                                       suffix=".avsc",
                                       prefix="wordcount",
                                       delete=False) as osfile:
        osfile.write(_OUT_SCHEMA)
      outschema = osfile.name

      if not(os.path.exists(outschema)):
        self.fail("Missing the schema file")

      outpath = os.path.join(base_dir, "out")

      args=[]

      args.append("java")
      args.append("-jar")
      args.append(os.path.abspath("@TOPDIR@/../java/tools/target/avro-tools-@AVRO_VERSION@.jar"))


      args.append("tether")
      args.extend(["--in",inpath])
      args.extend(["--out",outpath])
      args.extend(["--outschema",outschema])
      args.extend(["--protocol","http"])

      # form the arguments for the subprocess
      subargs=[]

      srcfile = avro.tether.tether_task_runner.__file__

      # Create a shell script to act as the program we want to execute
      # We do this so we can set the python path appropriately
      script="""#!/bin/bash
export PYTHONPATH={0}
python -m avro.tether.tether_task_runner word_count_task.WordCountTask
"""
      # We need to make sure avro is on the path
      # getsourcefile(avro) returns .../avro/__init__.py
      asrc = avro.__file__
      apath=asrc.rsplit(os.sep,2)[0]

      # path to where the tests lie
      tpath=os.path.split(__file__)[0]

      with tempfile.NamedTemporaryFile(mode='wb',
                                       prefix="exec_word_count_",
                                       delete=False) as exhf:
        exhf.write(script.format((os.pathsep).join([apath,tpath]),srcfile))
      exfile=exhf.name

      # make it world executable
      os.chmod(exfile,0o755)

      args.extend(["--program",exfile])

      print("Command:\n\t{0}".format(" ".join(args)))
      proc=subprocess.Popen(args)


      proc.wait()

      # read the output
      datum_reader = avro.io.DatumReader()
      outfile = os.path.join(outpath, "part-00000.avro")
      with avro.datafile.DataFileReader(open(outfile, 'rb'), datum_reader) as reader:
        for record in reader:
          self.assertEqual(record["value"],true_counts[record["key"]])
    finally:
      # close the process
      if proc is not None and proc.returncode is None:
        proc.kill()
      if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
      if exfile is not None and os.path.exists(exfile):
        os.remove(exfile)

if __name__== "__main__":
  unittest.main()
