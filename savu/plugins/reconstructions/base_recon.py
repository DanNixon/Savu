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
.. module:: base_recon
   :platform: Unix
   :synopsis: A base class for all reconstruction methods

.. moduleauthor:: Mark Basham <scientificsoftware@diamond.ac.uk>

"""
import math


from savu.plugins.plugin import Plugin
import numpy as np


class BaseRecon(Plugin):
    """
    A base class for reconstruction plugins

    :u*param centre_of_rotation: Centre of rotation to use for the \
    reconstruction. Default: 0.0.
    :u*param init_vol: Dataset to use as volume initialiser \
    (doesn't currently work with preview). Default: None.

    :param centre_pad: Pad the sinogram to centre it in order to fill the \
    reconstructed volume ROI for asthetic purposes - only available for \
    selected algorithms and will be ignored if unavailable (warning: This will\
    increase the size of the data and the time to compute the \
    reconstruction. Default: False.

    :param outer_pad: Pad the sinogram to fill the reconstructed volume for \
    asthetic purposes - only available for selected algorithms and if \
    centre_pad is True (warning: This will significantly increase the size of \
    the data and the time to compute the reconstruction). Default: False.

    :u*param log: Take the log of the data before reconstruction \
    (True or False). Default: True.
    :u*param preview: A slice list of required frames. Default: [].
    :param force_zero: Set any values in the reconstructed image outside of \
    this range to zero. Default: [None, None].
    to zero. Default: False.
    :param ratio: Ratio of the masks diameter in pixels to the smallest edge\
        size along given axis. Default: 0.95.
    """
    count = 0

    def __init__(self, name='BaseRecon'):
        super(BaseRecon, self).__init__(name)
        self.nOut = 1
        self.nIn = 1
        self.scan_dim = None
        self.rep_dim = None
        self.br_vol_shape = None
        self.frame_angles = None
        self.frame_cors = None
        self.frame_init_data = None
        self.centre = None
        self.base_pad_amount = None
        self.padding_alg = False
        self.cor_shift = 0

    def base_dynamic_data_info(self):
        if 'init_vol' in self.parameters.keys() and \
                                             self.parameters['init_vol']:
            if len(self.parameters['init_vol'].split('.')) is 3:
                name, temp, self.rep_dim = self.parameters['init_vol']
                self.parameters['init_vol'] = name
            self.nIn += 1
            self.parameters['in_datasets'].append(self.parameters['init_vol'])

    def base_pre_process(self):
        in_data, out_data = self.get_datasets()
        in_pData, out_pData = self.get_plugin_datasets()
        self.pad_dim = \
            in_pData[0].get_data_dimension_by_axis_label('x', contains=True)
        in_meta_data = self.get_in_meta_data()[0]
        self.__set_padding_alg()

        self.exp.log(self.name + " End")
        self.br_vol_shape = out_pData[0].get_shape()
        self.set_centre_of_rotation(in_data[0], in_meta_data, in_pData[0])

        self.main_dir = in_pData[0].get_pattern()['SINOGRAM']['main_dir']
        self.angles = in_meta_data.get('rotation_angle')
        if len(self.angles.shape) is not 1:
            self.scan_dim = in_data[0].get_data_dimension_by_axis_label('scan')
        self.slice_dirs = out_data[0].get_slice_dimensions()

        shape = in_pData[0].get_shape()
        pad_len = shape[self.pad_dim] if self.parameters['outer_pad'] else 0

        # this is the correct value but doesn't give a good result
        self.sino_pad = int(math.ceil((math.sqrt(2)-1)*pad_len))

        self.sino_func, self.cor_func = self.set_function(shape) if \
            self.padding_alg else self.set_function(False)

        self.range = self.parameters['force_zero']
        self.fix_sino = self.get_sino_centre_method()

    def __set_padding_alg(self):
        """ Determine if this is an algorithm that allows sinogram padding. """
        pad_algs = self.get_padding_algorithms()
        alg = self.parameters['algorithm'] if 'algorithm' in \
            self.parameters.keys() else None
        self.padding_alg = True if alg in pad_algs else False

    def get_vol_shape(self):
        return self.br_vol_shape

    def set_centre_of_rotation(self, inData, mData, pData):
        if 'centre_of_rotation' in mData.get_dictionary().keys():
            cor = mData.get('centre_of_rotation')
        else:
            sdirs = inData.get_slice_dimensions()
            cor = np.ones(np.prod([inData.get_shape()[i] for i in sdirs]))
            val = self.parameters['centre_of_rotation']
            # if centre of rotation has not been set then fix it in the centre
            val = val if val != 0 else \
                (self.get_vol_shape()[self._get_detX_dim()])/2
            cor *= val
            #mData.set('centre_of_rotation', cor) see Github ticket
        self.cor = cor
        self.centre = self.cor[0]

    def set_function(self, pad_shape):
        if not pad_shape:
            cor_func = lambda cor: cor
            if self.parameters['log']:
                sino_func = lambda sino: -np.log(np.nan_to_num(sino)+1)
            else:
                sino_func = lambda sino: np.nan_to_num(sino)
        else:
            mode = 'edge'
            cor_func = lambda cor: cor+self.sino_pad
            pad_tuples = [(0, 0)]*(len(pad_shape)-1)
            pad_tuples.insert(self.pad_dim, (self.sino_pad, self.sino_pad))
            pad_tuples = tuple(pad_tuples)
            if self.parameters['log']:
                sino_func = lambda sino: -np.log(np.nan_to_num(
                    np.pad(sino, pad_tuples, mode))+1)
            else:
                sino_func = lambda sino: np.nan_to_num(np.pad(
                    sino, pad_tuples, mode))
        return sino_func, cor_func

    def base_process_frames_before(self, data):
        """
        Reconstruct a single sinogram with the provided centre of rotation
        """
        sl = self.get_current_slice_list()[0]
        init = data[1] if len(data) is 2 else None
        angles = \
            self.angles[:, sl[self.scan_dim]] if self.scan_dim else self.angles
        self.frame_angles = angles

        dim_sl = sl[self.main_dir]

        global_frames = self.get_global_frame_index()[0][self.count]

        self.frame_cors = self.cor_func(self.cor[[global_frames]])

        # for extra padded frames that make up the numbers
        if not self.frame_cors.shape:
            self.frame_cors = np.array([self.centre])

        len_data = len(np.arange(dim_sl.start, dim_sl.stop, dim_sl.step))

        missing = [self.centre]*(len(self.frame_cors) - len_data)
        self.frame_cors = np.append(self.frame_cors, missing)

        self.frame_init_data = init
        data[0] = self.fix_sino(self.sino_func(data[0]), self.frame_cors[0])
        return data

    def base_process_frames_after(self, data):
        lower_range, upper_range = self.range
        if lower_range is not None:
            data[data < lower_range] = 0
        if upper_range is not None:
            data[data > upper_range] = 0
        return data

    def get_padding_algorithms(self):
        """ A list of algorithms that allow the data to be padded. """
        return []

    def pad_sino(self, sino, cor):
        """  Pad the sinogram so the centre of rotation is at the centre. """
        detX = self._get_detX_dim()
        pad = self.get_centre_offset(sino, cor, detX)
        self.cor_shift = pad[0]
        pad_tuples = [(0, 0)]*(len(sino.shape)-1)
        pad_tuples.insert(detX, tuple(pad))
        self.__set_pad_amount(max(pad))
        return np.pad(sino, tuple(pad_tuples), mode='edge')

    def _get_detX_dim(self):
        pData = self.get_plugin_in_datasets()[0]
        return pData.get_data_dimension_by_axis_label('x', contains=True)

    def get_centre_offset(self, sino, cor, detX):
        centre_pad = self.br_array_pad(cor, sino.shape[detX])
        sino_width = sino.shape[detX]
        new_width = sino_width + max(centre_pad)
        sino_pad = \
            int(math.ceil(float(sino_width)/new_width * self.sino_pad)/2)
        pad = np.array([sino_pad]*2) + centre_pad
        return pad

    def get_centre_shift(self, sino, cor):
        detX = self._get_detX_dim()
        return max(self.get_centre_offset(sino, self.centre, detX))

    def crop_sino(self, sino, cor):
        """  Crop the sinogram so the centre of rotation is at the centre. """
        detX = self._get_detX_dim()
        start, stop = self.br_array_pad(cor, sino.shape[detX])[::-1]
        self.cor_shift = -start
        sl = [slice(None)]*len(sino.shape)
        sl[detX] = slice(start, sino.shape[detX] - stop)
        sino = sino[tuple(sl)]
        self.set_mask(sino.shape)
        return sino

    def br_array_pad(self, ctr, nPixels):
        width = nPixels - 1.0
        alen = ctr
        blen = width - ctr
        mid = (width-1.0)/2.0
        shift = round(abs(blen-alen))
        p_low = 0 if (ctr > mid) else shift
        p_high = shift + 0 if (ctr > mid) else 0
        return np.array([int(p_low), int(p_high)])

    def keep_sino(self, sino, cor):
        """ No change to the sinogram """
        return sino

    def get_sino_centre_method(self):
        centre_pad = self.keep_sino
        if 'centre_pad' in self.parameters.keys():
            centre_pad = self.pad_sino if self.parameters['centre_pad'] and \
                self.padding_alg is True else self.crop_sino
        return centre_pad

    def __set_pad_amount(self, pad_amount):
        self.base_pad_amount = pad_amount

    def get_pad_amount(self):
        return self.base_pad_amount

    def get_fov_fraction(self, sino, cor):
        """ Get the fraction of the original FOV that can be reconstructed due\
        to offset centre """
        pData = self.get_plugin_in_datasets()[0]
        detX = pData.get_data_dimension_by_axis_label('x', contains=True)
        original_length = sino.shape[detX]
        shift = self.get_centre_shift(sino, cor)
        return (original_length-shift)/float(original_length)

    def get_reconstruction_alg(self):
        return None

    def get_angles(self):
        """ Get the angles associated with the current sinogram(s).

        :returns: Angles of the current frames.
        :rtype: np.ndarray
        """
        return self.frame_angles

    def get_cors(self):
        """
        Get the centre of rotations associated with the current sinogram(s).

        :returns: Centre of rotation values for the current frames.
        :rtype: np.ndarray
        """
        return self.frame_cors + self.cor_shift

    def set_mask(self, shape):
        pass

    def get_initial_data(self):
        """
        Get the initial data (if it is exists) associated with the current \
        sinogram(s).

        :returns: The section of the initialisation data associated with the \
            current frames.
        :rtype: np.ndarray or None
        """
        return self.frame_init_data

    def get_frame_params(self):
        params = [self.get_cors(), self.get_angles(), self.get_vol_shape(),
                  self.get_initial_data()]
        return params

    def setup(self):
        in_dataset, out_dataset = self.get_datasets()
        # reduce the data as per data_subset parameter
        self.preview_flag = \
            self.set_preview(in_dataset[0], self.parameters['preview'])

        # set information relating to the plugin data
        in_pData, out_pData = self.get_plugin_datasets()

        in_pData[0].plugin_data_setup('SINOGRAM', self.get_max_frames())
        if len(in_pData) is 2:
            from savu.data.data_structures.data_types import Replicate
            if self.rep_dim:
                in_dataset[1].data = Replicate(
                    in_dataset[1], in_dataset[0].get_shape(self.rep_dim))
            in_pData[1].plugin_data_setup('VOLUME_XZ', self.get_max_frames())

        axis_labels = in_dataset[0].data_info.get('axis_labels')[0]

        dim_volX, dim_volY, dim_volZ = \
            self.map_volume_dimensions(in_dataset[0], in_pData[0])

        axis_labels = [0]*3
        axis_labels = {in_dataset[0]:
                       [str(dim_volX) + '.voxel_x.voxels',
                        str(dim_volY) + '.voxel_y.voxels',
                        str(dim_volZ) + '.voxel_z.voxels']}

        shape = list(in_dataset[0].get_shape())
        shape[dim_volX] = shape[dim_volZ]

        if 'resolution' in self.parameters.keys():
            shape[dim_volX] /= self.parameters['resolution']
            shape[dim_volZ] /= self.parameters['resolution']

        out_dataset[0].create_dataset(axis_labels=axis_labels,
                                      shape=tuple(shape))

        out_dataset[0].add_volume_patterns(dim_volX, dim_volY, dim_volZ)

        # set pattern_name and nframes to process for all datasets
        out_pData[0].plugin_data_setup('VOLUME_XZ', self.get_max_frames())

    def get_max_frames(self):
        return 'multiple'

    def map_volume_dimensions(self, data, pData):
        data._finalise_patterns()
        dim_rotAngle = data.get_data_patterns()['PROJECTION']['main_dir']
        dim_detY = data.get_data_patterns()['SINOGRAM']['main_dir']

        core_dirs = data.get_core_dimensions()
        dim_detX = list(set(core_dirs).difference(set((dim_rotAngle,))))[0]

        dim_volX = dim_rotAngle
        dim_volY = dim_detY
        dim_volZ = dim_detX
        return dim_volX, dim_volY, dim_volZ

    def nInput_datasets(self):
        return self.nIn

    def nOutput_datasets(self):
        return self.nOut

    def reconstruct_pre_process(self):
        """
        Should be overridden to perform pre-processing in a child class
        """
        pass

    def executive_summary(self):
        summary = []
        if not self.preview_flag:
            summary.append(("WARNING: Ignoring preview parameters as a preview"
                            " has already been applied to the data."))
        if len(summary) > 0:
            return summary
        return ["Nothing to Report"]
