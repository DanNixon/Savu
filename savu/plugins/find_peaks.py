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
.. module:: find_peaks
   :platform: Unix
   :synopsis: A plugin to find the peaks

.. moduleauthor:: Aaron Parsons <scientificsoftware@diamond.ac.uk>

"""
from savu.plugins.driver.cpu_plugin import CpuPlugin


from savu.plugins.utils import register_plugin
from savu.plugins.base_filter import BaseFilter
import peakutils as pe
import numpy as np
from scipy.signal import savgol_filter
from itertools import chain


@register_plugin
class FindPeaks(BaseFilter, CpuPlugin):
    """
    This plugin uses peakutils to find peaks in spectra. This is then metadata.
    :param in_datasets: Create a list of the dataset(s). Default: [].
    :param out_datasets: Create a list of the dataset(s). Default: [].
    :param thresh: Threshold for peak detection Default: 0.03.
    :param min_distance: Minimum distance for peak detection. Default: 15.
    """

    def __init__(self):
        super(FindPeaks, self).__init__("FindPeaks")

    def filter_frames(self, data):
        _in_meta_data, out_meta_data = self.get_meta_data()
        data = savgol_filter(data[0].squeeze(), 51, 3)
        PeakIndex = list(out_meta_data[0].get_meta_data('PeakIndex'))
        PeakIndexNew = list(pe.indexes(data, thres=self.parameters['thresh'],
                            min_dist=self.parameters['min_distance']))
        # print type(PeakIndex), 'boo', type(PeakIndexNew)
        # print 'Im here'
        PeakIndexNew = list(PeakIndexNew)
        wind = self.parameters['min_distance']
        set2 = set(list(chain.from_iterable(range(x-wind/2,
                                                  x+wind/2, 1)
                                            for x in PeakIndex)))
        tmp = set(PeakIndexNew) - set2
        tmp = list(tmp)
        print 'temp is ', sorted(tmp)
        print 'New index is', sorted(PeakIndexNew)
        print 'old index is', sorted(PeakIndex)
        PeakIndex.extend(tmp)
        out_meta_data[0].set_meta_data('PeakIndex', PeakIndex)
        return np.array(PeakIndex)

    def post_process(self):
        # remove the output dataset from the processing chain
        self.exp.remove_dataset(self.get_out_datasets()[0])

    def setup(self):
        # set up the output dataset that is created by the plugin
        in_dataset, out_dataset = self.get_datasets()
        # set information relating to the plugin data
        in_pData, out_pData = self.get_plugin_datasets()
        # set pattern_name and nframes to process for all datasets
        in_pData[0].plugin_data_setup("SPECTRUM", self.get_max_frames())

        nFrames = in_pData[0].get_total_frames()
        out_dataset[0].create_dataset(axis_labels=('y.pixels',), # the axis label needs changing
                                      shape={'variable': (nFrames,)},
                                      dtype=np.int)  # default is float32
        out_dataset[0].add_pattern("1D_METADATA", slice_dir=(0,))
        out_dataset[0].meta_data.set_meta_data('PeakIndex', [])

        out_pData[0].plugin_data_setup("1D_METADATA", self.get_max_frames())

    def get_max_frames(self):
        """
        This filter processes 1 frame at a time

         :returns:  1
        """
        return 1