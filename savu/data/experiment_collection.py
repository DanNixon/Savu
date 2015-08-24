# Copyright 2014 Diamond Light Source Ltd.
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

"""
.. module:: experiment_collection
   :platform: Unix
   :synopsis: Contains the Experiment class and all possible experiment 
   collections from which Experiment can inherit at run time.

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""

from savu.data.plugin_list import PluginList
from savu.data.data_structures import Data
from savu.data.meta_data import MetaData

class Experiment(object):
    """
    One instance of this class is created at the beginning of the 
    processing chain and remains until the end.  It holds the current data
    object and a dictionary containing all metadata.
    """
   
    def __init__(self, options):
        self.meta_data = MetaData(options)
        self.meta_data_setup(options["process_file"])
        self.index = {"in_data": {}, "out_data": {}}
  

    def meta_data_setup(self, process_file):
        self.meta_data.load_experiment_collection()
        self.meta_data.plugin_list = PluginList()
        self.meta_data.plugin_list.populate_plugin_list(process_file)


    def create_data_object(self, dtype, name, bases=[]):
        self.index[dtype][name] = Data()
        data_obj = self.index[dtype][name]
        bases.append(data_obj.get_transport_data(self.meta_data.get_meta_data("transport")))
        data_obj.add_base_classes(bases)        
        return self.index[dtype][name]