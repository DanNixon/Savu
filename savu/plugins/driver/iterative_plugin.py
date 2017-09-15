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
.. module:: iterative_plugin
   :platform: Unix
   :synopsis: Driver for iterative plugins

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""

from savu.plugins.driver.plugin_driver import PluginDriver


class IterativePlugin(PluginDriver):
    """
    Allows the plugin to be repeated, keeping the parameters from the previous
    iteration.
    """

    def __init__(self):
        super(IterativePlugin, self).__init__()
        self._ip_iteration = 0
        self._ip_fixed_iterations = False
        self._ip_complete = False
        self._ip_data_dict = {}
        self._ip_data_dict['iterating'] = {}

    def _run_plugin(self, exp, transport):
        """ Runs the pre_process, process and post_process methods.
        """
        while not self._ip_complete:
            print "...Plugin iteration", self._ip_iteration+1
            self.__set_datasets()
            self._perform_the_processing(transport)
            if self._ip_fixed_iterations and \
                    self._ip_iteration == self._ip_fixed_iterations-1:
                self.set_processing_complete()
            self._ip_iteration += 1
        self.__finalise_datasets()

    def __set_datasets(self):
        params = self.parameters
        if self._ip_iteration in self._ip_data_dict.keys():
            params['in_datasets'] = self._ip_data_dict[self._ip_iteration][0]
            params['out_datasets'] = self._ip_data_dict[self._ip_iteration][1]
        elif self._ip_iteration > 0:
            p = [params['in_datasets'], params['out_datasets']]
            for s1, s2 in self._ip_data_dict['iterating'].iteritems():
                a = [0, p[0].index(s1)] if s1 in p[0] else [1, p[1].index(s1)]
                b = [0, p[0].index(s2)] if s2 in p[0] else [1, p[1].index(s2)]
                p[a[0]][a[1]], p[b[0]][b[1]] = p[b[0]][b[1]], p[a[0]][a[1]]

    def get_iteration(self):
        return self._ip_iteration

    def __finalise_datasets(self):
        for s1, s2 in self._ip_data_dict['iterating'].iteritems():
            name = s1.get_name()
            name = name if 'itr_clone' not in name else s2.get_name()
            final_dataset = s1 if s1 in self.parameters['out_datasets'] else s2
            obsolete = s1 if s1 is not final_dataset else s2
            obsolete.remove = True
            final_dataset._set_name(name)

    def set_processing_complete(self):
        self._ip_complete = True

    def set_iterations(self, nIterations):
        if isinstance(nIterations, int):
            self._ip_fixed_iterations = nIterations
        else:
            raise Exception('nIterations should be an integer.')

    def set_iteration_datasets(self, itr, in_data, out_data):
        self._ip_data_dict[itr] = [in_data, out_data]

    def set_alternating_datasets(self, d1, d2):
        names = [d1.get_name(), d2.get_name()]
        if not any([True if 'itr_clone' in i else False for i in names]):
            raise Exception('Alternating datasets must contain a clone.  These'
                            ' are found at the end of the out_datasets list')
        self._ip_data_dict['iterating'][d1] = d2

    def get_alternating_datasets(self):
        return self._ip_data_dict['iterating']
