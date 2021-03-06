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
.. module:: yaml_loader
   :platform: Unix
   :synopsis: A class to load data from a non-standard nexus/hdf5 file using \
   descriptions loaded from a yaml file.

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""

import h5py
import yaml
import collections
import numpy as np # used in exec so do not delete

import savu.plugins.utils as pu
import savu.plugins.loaders.utils.yaml_utils as yu
from savu.plugins.loaders.base_loader import BaseLoader


class YamlConverter(BaseLoader):
    """
    A class to load data from a non-standard nexus/hdf5 file using \
    descriptions loaded from a yaml file.

    :u*param yaml_file: Path to the file containing the data \
        descriptions. Default: None.
    :*param template_param: A hidden parameter to hold parameters passed in \
        via a savu template file. Default: {}.
    """

    def __init__(self, name='YamlConverter'):
        super(YamlConverter, self).__init__(name)

    def setup(self, template=False):
        #  Read YAML file
        if self.parameters['yaml_file'] is None:
            raise Exception('Please pass a yaml file to the yaml loader.')

        data_dict = yu.read_yaml(self.parameters['yaml_file'])
        data_dict = self._check_for_inheritance(data_dict, {})
        self._check_for_imports(data_dict)
        data_dict.pop('inherit', None)
        data_dict.pop('import', None)
        if template:
            return data_dict

        data_dict = self._add_template_updates(data_dict)
        self._set_entries(data_dict)

    def _add_template_updates(self, ddict):
        all_entries = ddict.pop('all', {})
        for key, value in all_entries:
            for entry in ddict:
                if key in entry.keys():
                    entry[key] = value

        for entry in self.parameters['template_param']:
            updates = self.parameters['template_param'][entry]
            ddict[entry]['params'].update(updates)
        return ddict

    def _check_for_imports(self, ddict):
        if 'import' in ddict.keys():
            for imp in ddict['import']:
                name = False
                if len(imp.split()) > 1:
                    imp, name = imp.split('as')
                mod = __import__(imp.strip())
                globals()[mod.__name__ if not name else name] = mod

    def _check_for_inheritance(self, ddict, inherit):
        if 'inherit' in ddict.keys():
            idict = ddict['inherit']
            idict = idict if isinstance(idict, list) else [idict]
            for i in idict:
                if i != 'None':
                    new_dict = yu.read_yaml(i)
                    inherit.update(new_dict)
                    inherit = self._check_for_inheritance(new_dict, inherit)
        self._update(inherit, ddict)
        return inherit

    def _update(self, d, u):
        for k, v in u.iteritems():
            if isinstance(v, collections.Mapping):
                d[k] = self._update(d.get(k, {}), v)
            else:
                d[k] = v
        return d

    def _set_entries(self, ddict):
        entries = ddict.keys()
        for name in entries:
            self.get_description(ddict[name], name)

    def get_description(self, entry, name):
        # set params first as we may need them subsequently
        if 'params' in entry:
            self._set_params(entry['params'])

        # --------------- check for data entry -----------------------------
        if 'data' in entry.keys():
            data_obj = self.exp.create_data_object("in_data", name)
            data_obj = self.set_data(data_obj, entry['data'])
        else:
            emsg = 'Please specify the data information in the yaml file.'
            raise Exception(emsg)

        # --------------- check for axis label information -----------------
        if 'axis_labels' in entry.keys():
            self._set_axis_labels(data_obj, entry['axis_labels'])
        else:
            raise Exception('Please specify the axis labels in the yaml file.')

        # --------------- check for data access patterns -------------------
        if 'patterns' in entry.keys():
            self._set_patterns(data_obj, entry['patterns'])
        else:
            raise Exception('Please specify the patterns in the yaml file.')

        # add any additional metadata
        if 'metadata' in entry:
            self._set_metadata(data_obj, entry['metadata'])
        self.set_data_reduction_params(data_obj)

    def set_data(name, entry):
        raise NotImplementedError('Please implement "get_description" function'
                                  'in the loader')

    def _set_keywords(self, dObj):
        filepath = str(dObj.backing_file.filename)
        shape = str(dObj.get_shape())
        return {'dfile': filepath, 'dshape': shape}

    def update_value(self, dObj, value):
        # setting the keywords
        if dObj is not None:
            dshape = dObj.get_shape()
            dfile = dObj.backing_file
        if isinstance(value, str):
            split = value.split('$')
            if len(split) > 1:
                value = self._convert_string(dObj, split[1])
                exec('value = ' + value)
        return value

    def _convert_string(self, dObj, string):
        for old, new in self.parameters.iteritems():
            if old in string:
                if isinstance(new, str):
                    split = new.split('$')
                    if len(split) > 1:
                        new = split[1]
                    elif isinstance(new, str):
                        new = "'%s'" % new
                string = self._convert_string(
                        dObj, string.replace(old, str(new)))
        return string

    def _set_params(self, params):
        # Update variable parameters that are revealed in the template
        params = self._update_template_params(params)
        self.parameters.update(params)
        # find files, open and add to the namespace then delete file params
        files = [k for k in params.keys() if k.endswith('file')]
        for f in files:
            globals()[str(f)] = self.update_value(None, params[f])
            del params[f]

    def _update_template_params(self, params):
        for k, v in params.iteritems():
            v = pu.is_template_param(v)
            if v is not False:
                params[k] = \
                    self.parameters[k] if k in self.parameters.keys() else v[1]
        return params

    def _set_axis_labels(self, dObj, labels):
        dims = range(len(labels.keys()))
        axis_labels = [None]*len(labels.keys())
        for d in dims:
            self._check_label_entry(labels[d])
            l = labels[d]
            for key in l.keys():
                l[key] = self.update_value(dObj, l[key])
            axis_labels[l['dim']] = (l['name'] + '.' + l['units'])
            if l['value'] is not None:
                dObj.meta_data.set(l['name'], l['value'])
        dObj.set_axis_labels(*axis_labels)

    def _check_label_entry(self, label):
        required = ['dim', 'name', 'value', 'units']
        try:
            [label[i] for i in required]
        except:
            raise Exception("name, value and units are required fields for \
                            axis labels")

    def _set_patterns(self, dObj, patterns):
        for key, dims in patterns.iteritems():
            core_dims = self.update_value(dObj, dims['core_dims'])
            slice_dims = self.update_value(dObj, dims['slice_dims'])
            dObj.add_pattern(key, core_dims=core_dims, slice_dims=slice_dims)

    def _set_metadata(self, dObj, mdata):
        for key, value in mdata.iteritems():
            value = self.update_value(dObj, value['value'])
            dObj.meta_data.set(key, value)
