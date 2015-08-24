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
.. module:: hdf5_transport_data
   :platform: Unix
   :synopsis: A data transport class that is inherited by Data class at 
   runtime. It performs the movement of the data, including loading and saving.

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""
import os
import logging 

import numpy as np

import savu.data.data_structures as ds
from savu.core.utils import logmethod

class Hdf5TransportData(object):
    """
    The Hdf5TransportData class performs the loading and saving of data 
    specific to a hdf5 transport mechanism.
    """
            
    def __init__(self):
        self.backing_file = None

    
    def load_data(self, plugin_runner, exp):

        plugin_list = exp.meta_data.plugin_list.plugin_list
        final_plugin = plugin_list[-1]
        saver_plugin = plugin_runner.load_plugin(final_plugin["id"])

        logging.debug("generating all output files")
        out_data_objects = []
        count = 0
        for plugin_dict in plugin_list[1:-1]:
            
            plugin_id = plugin_dict["id"]
            logging.debug("Loading plugin %s", plugin_id)
            plugin = plugin_runner.load_plugin(plugin_id)
            plugin.setup(exp)
            
            self.set_filenames(exp, plugin, plugin_id, count)

            saver_plugin.setup(exp)
            
            out_data_objects.append(exp.index["out_data"].copy())
            
            count += 1
            
        return out_data_objects

    
    def set_filenames(self, exp, plugin, plugin_id, count):
        expInfo = exp.meta_data
        expInfo.set_meta_data("filename", {})
        expInfo.set_meta_data("group_name", {})
        for key in exp.index["out_data"].keys():
            filename = os.path.join(expInfo.get_meta_data("out_path"),"%s%02i_%s" % \
                                    (os.path.basename(expInfo.get_meta_data("process_file")),
                                    count, plugin_id))
            filename = filename + "_" + key + ".h5"
            group_name = "%i-%s" % (count, plugin.name)
            logging.debug("Creating output file %s", filename)
            expInfo.set_meta_data(["filename", key], filename)
            expInfo.set_meta_data(["group_name", key], group_name)

        
    def save_data(self):
        """
        Closes the backing file and completes work
        """
        if self.backing_file is not None:
            logging.debug("Completing file %s",self.backing_file.filename)
            self.backing_file.close()
            self.backing_file = None


    def get_slice_list(self):
        
        it = np.nditer(self.data, flags=['multi_index'])
        dirs_to_remove = list(self.get_core_directions())
        
        dirs_to_remove.sort(reverse=True)
        for direction in dirs_to_remove:
            it.remove_axis(direction)
        mapping_list = range(len(it.multi_index))        
        dirs_to_remove.sort()
        for direction in dirs_to_remove:
            mapping_list.insert(direction, -1)
        mapping_array = np.array(mapping_list)
        slice_list = []
        while not it.finished:
            tup = it.multi_index + (slice(None),)
            slice_list.append(tuple(np.array(tup)[mapping_array]))
            it.iternext()
            
        return slice_list

    
    def calc_step(self, slice_a, slice_b):
        result = []
        for i in range(len(slice_a)):
            if slice_a[i] == slice_b[i]:
                result.append(0)
            else:
                result.append(slice_b[i] - slice_a[i])
        return result


    def group_slice_list(self, slice_list, max_frames):
        banked = []
        batch = []
        step = -1
        for sl in slice_list:
            if len(batch) == 0:
                batch.append(sl)
                step = -1
            elif step == -1:
                new_step = self.calc_step(batch[-1], sl)
                # check stepping in 1 direction
                if (np.array(new_step) > 0).sum() > 1:
                    # we are stepping in multiple directions, end the batch
                    banked.append((step, batch))
                    batch = []
                    batch.append(sl)
                    step = -1
                else:
                    batch.append(sl)
                    step = new_step
            else:
                new_step = self.calc_step(batch[-1], sl)
                if new_step == step:
                    batch.append(sl)
                else:
                    banked.append((step, batch))
                    batch = []
                    batch.append(sl)
                    step = -1
        banked.append((step, batch))
    
        # now combine the groups into single slices
        grouped = []
        for step, group in banked:
            working_slice = list(group[0])
            step_dir = step.index(max(step))
            start = group[0][step_dir]
            stop = group[-1][step_dir]
            for i in range(start, stop, max_frames):
                new_slice = slice(i, i+max_frames, step[step_dir])
                working_slice[step_dir] = new_slice
                grouped.append(tuple(working_slice))
        return grouped
    
    
    def get_grouped_slice_list(self):
        max_frames = self.get_nFrames()
        max_frames = (1 if max_frames is None else max_frames)

        sl = self.get_slice_list()
        
        if isinstance(self, ds.TomoRaw):
            sl = self.get_frame_raw(sl)
        
        if sl is None:
            raise Exception("Data type", self.get_current_pattern_name(), 
                            "does not support slicing in directions", 
                            self.get_slice_directions())
            
        gsl = self.group_slice_list(sl, max_frames)
        return gsl


    def get_slice_list_per_process(self, expInfo):
        processes = expInfo.get_meta_data("processes")
        process = expInfo.get_meta_data("process")
        slice_list = self.get_grouped_slice_list()
        
        frame_index = np.arange(len(slice_list))
        frames = np.array_split(frame_index, len(processes))[process]
        return [ slice_list[frames[0]:frames[-1]+1], frame_index ]
        

class SliceAvailableWrapper(object):
    """
    This class takes 2 datasets, one available boolean ndarray, and 1 data
    ndarray.  Its purpose is to provide slices from the data array only if data
    has been put there, and to allow a convenient way to put slices into the
    data array, and set the available array to True
    """
    def __init__(self, avail, data):
        """
        :param avail: The available boolean ndArray
        :type avail: boolean ndArray
        :param data: The data ndArray
        :type data: any ndArray
        """
        self.avail = avail
        self.data = data

        
    def __deepcopy__(self, memo):
        return self
        
        
    def __getitem__(self, item):
        if self.avail[item].all():
            #return np.squeeze(self.data[item])
            return self.data[item]
        else:
            return None


    def __setitem__(self, item, value):
        #self.data[item] = value.reshape(self.data[item].shape)
        self.data[item] = value
        self.avail[item] = True
        return np.squeeze(self.data[item])
        
        
    def __getattr__(self, name):
        """
        Delegate everything else to the data class
        """
        value = self.data.__getattribute__(name)
        return value


class SliceAlwaysAvailableWrapper(SliceAvailableWrapper):
    """
    This class takes 1 data ndarray.  Its purpose is to provide slices from the
    data array in the same way as the SliceAvailableWrapper but assuming the
    data is always available (for example in the case of the input file)
    """
    def __init__(self, data):
        """

        :param data: The data ndArray
        :type data: any ndArray
        """
        super(SliceAlwaysAvailableWrapper, self).__init__(None, data)

    @logmethod
    def __getitem__(self, item):
        return self.data[item]

    @logmethod
    def __setitem__(self, item, value):
        self.data[item] = value