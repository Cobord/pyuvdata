from astropy import constants as const
from astropy.time import Time
from astropy.io import fits
import os.path as op
import numpy as np
from scipy.io.idl import readsav
import pandas as pd
import warnings
from itertools import islice


class uv_property:
    def __init__(self, required=True, value=None, spoof_val=None, units=None,
                 description=''):
        self.required = required
        # cannot set a spoof_val for required properties
        if not self.required:
            self.spoof_val = spoof_val
        self.value = value
        self.units = units
        self.description = description

    def apply_spoof(self, *args):
        self.value = self.spoof_val


class ant_position_uv_property(uv_property):
    def apply_spoof(self, uvdata):
        self.value = np.zeros((uvdata.Nants.value, 3))


class extra_dict_uv_property(uv_property):
    def __init__(self, required=True, value={}, spoof_val={}, units=None,
                 description=''):
        self.required = required
        # cannot set a spoof_val for required properties
        if not self.required:
            self.spoof_val = spoof_val
        self.value = value
        self.units = units
        self.description = description


class UVData:
    supported_file_types = ['uvfits', 'miriad', 'fhd']

    uvfits_required_extra = ['xyz_telescope_frame', 'x_telescope',
                             'y_telescope', 'z_telescope',
                             'antenna_positions', 'GST0', 'RDate',
                             'earth_omega', 'DUT1', 'TIMESYS']

    def __init__(self):
        # add the default_required_attributes to the class?
        # dimension definitions
        self.Ntimes = uv_property(description='Number of times')
        self.Nbls = uv_property(description='number of baselines')
        self.Nblts = uv_property(description='Ntimes * Nbls')
        self.Nfreqs = uv_property(description='number of frequency channels')
        self.Npols = uv_property(description='number of polarizations')

        desc = ('array of the visibility data, size: (Nblts, Nspws, Nfreqs, ' +
                'Npols), type = complex float, in units of self.vis_units')
        self.data_array = uv_property(description=desc)

        self.vis_units = uv_property(description='Visibility units, options ' +
                                     '["uncalib","Jy","K str"]')

        desc = ('number of data points averaged into each data element, ' +
                'type = int, same shape as data_array')
        self.nsample_array = uv_property(description=desc)

        self.flag_array = uv_property(description='boolean flag, True is ' +
                                      'flagged, same shape as data_array.')

        self.Nspws = uv_property(description='number of spectral windows ' +
                                 '(ie non-contiguous spectral chunks)')

        self.spw_array = uv_property(description='array of spectral window ' +
                                     'numbers')

        desc = ('phase center of projected baseline vectors, (3,Nblts), ' +
                'units meters')
        self.uvw_array = uv_property(description=desc)

        self.time_array = uv_property(description='array of times, center ' +
                                      'of integration, (Nblts), julian date')

        desc = ('array of first antenna indices, dimensions (Nblts), ' +
                'type = int, 0 indexed')
        self.ant_1_array = uv_property(description=desc)
        desc = ('array of second antenna indices, dimensions (Nblts), ' +
                'type = int, 0 indexed')
        self.ant_2_array = uv_property(description=desc)

        desc = ('array of baseline indices, dimensions (Nblts), ' +
                'type = int; baseline = 2048 * (ant2+1) + (ant1+1) + 2^16 ' +
                '(may this break casa?)')
        self.baseline_array = uv_property(description=desc)

        self.freq_array = uv_property(description='array of frequencies, ' +
                                      'dimensions (Nspws,Nfreqs), units Hz')

        desc = ('array of polarization integers (Npols). ' +
                'AIPS Memo 117 says: stokes 1:4 (I,Q,U,V);  ' +
                'circular -1:-4 (RR,LL,RL,LR); linear -5:-8 (XX,YY,XY,YX)')
        self.polarization_array = uv_property(description=desc)

        desc = ('right ascension of phase center (see uvw_array), ' +
                'units degrees')
        self.phase_center_ra = uv_property(description=desc)

        desc = ('declination of phase center (see uvw_array), ' +
                'units degrees')
        self.phase_center_dec = uv_property(description=desc)

        self.integration_time = uv_property(description='length of the ' +
                                            'integration (s)')
        self.channel_width = uv_property(description='width of channel (Hz)')

        # --- observation information ---
        self.object_name = uv_property(description='source or field ' +
                                       'observed (string)')
        self.telescope_name = uv_property(description='name of telescope ' +
                                          '(string)')
        self.instrument = uv_property(description='receiver or backend.')
        self.latitude = uv_property(description='latitude of telescope, ' +
                                    'units degrees')
        self.longitude = uv_property(description='longitude of telescope, ' +
                                     'units degrees')
        self.altitude = uv_property(description='altitude of telescope, ' +
                                    'units meters')
        self.dateobs = uv_property(description='date of observation start, ' +
                                   'units JD.')
        self.history = uv_property(description='string of history, units ' +
                                   'English')

        desc = ('epoch year of the phase applied to the data (eg 2000)')
        self.phase_center_epoch = uv_property(description=desc)

        # --- antenna information ----
        self.Nants = uv_property(description='number of antennas')
        desc = ('list of antenna names, dimensions (Nants), ' +
                'indexed by self.ant_1_array, self.ant_2_array, ' +
                'self.antenna_indices')
        self.antenna_names = uv_property(description=desc)

        desc = ('integer index into antenna_names, dimensions ' +
                '(Nants), there must be one entry here for each unique ' +
                'entry in self.ant_1_array and self.ant_2_array, but there ' +
                'may be extras as well.')
        self.antenna_indices = uv_property(description=desc)

        desc = ('any user supplied extra keywords, type=dict')
        self.extra_keywords = extra_dict_uv_property(description=desc)

        # -------- extra, non-required properties ----------
        desc = ('coordinate frame for antenna positions ' +
                '(eg "ITRF" -also google ECEF). NB: ECEF has x running ' +
                'through long=0 and z through the north pole')
        self.xyz_telescope_frame = uv_property(required=False,
                                               description=desc,
                                               spoof_val='ITRF')

        self.x_telescope = uv_property(required=False,
                                       description='x coordinates of array ' +
                                       'center in meters in coordinate frame',
                                       spoof_val=0)
        self.y_telescope = uv_property(required=False,
                                       description='y coordinates of array ' +
                                       'center in meters in coordinate frame',
                                       spoof_val=0)
        self.z_telescope = uv_property(required=False,
                                       description='z coordinates of array ' +
                                       'center in meters in coordinate frame',
                                       spoof_val=0)
        desc = ('array giving coordinates of antennas relative to ' +
                '{x,y,z}_telescope in the same frame, (Nants,3)')
        self.antenna_positions = ant_position_uv_property(required=False,
                                                          description=desc)

        # --- other stuff ---
        # the below are copied from AIPS memo 117, but could be revised to
        # merge with other sources of data.
        self.GST0 = uv_property(required=False,
                                description='Greenwich sidereal time at ' +
                                'midnight on reference date', spoof_val=0)
        self.RDate = uv_property(required=False,
                                 description='date for which the GST0 or ' +
                                 'whatever... applies', spoof_val=0)
        self.earth_omega = uv_property(required=False,
                                       description='earth\'s rotation rate ' +
                                       'in degrees per day', spoof_val=360.985)
        self.DUT1 = uv_property(required=False,
                                description='DUT1 (google it) AIPS 117 ' +
                                'calls it UT1UTC', spoof_val=0.0)
        self.TIMESYS = uv_property(required=False,
                                   description='We only support UTC',
                                   spoof_val='UTC')

        desc = ('FHD thing we do not understand, something about the time ' +
                'at which the phase center is normal to the chosen UV plane ' +
                'for phasing')
        self.uvplane_reference_time = uv_property(required=False,
                                                  description=desc,
                                                  spoof_val=0)

    def property_iter(self):
        attribute_list = [a for a in dir(self) if not a.startswith('__') and
                          not callable(getattr(self, a))]
        prop_list = []
        for a in attribute_list:
            attr = getattr(self, a)
            if isinstance(attr, uv_property):
                prop_list.append(a)
        for a in prop_list:
            yield a

    def required_property_iter(self):
        attribute_list = [a for a in dir(self) if not a.startswith('__') and
                          not callable(getattr(self, a))]
        required_list = []
        for a in attribute_list:
            attr = getattr(self, a)
            if isinstance(attr, uv_property):
                if attr.required:
                    required_list.append(a)
        for a in required_list:
            yield a

    def extra_property_iter(self):
        attribute_list = [a for a in dir(self) if not a.startswith('__') and
                          not callable(getattr(self, a))]
        extra_list = []
        for a in attribute_list:
            attr = getattr(self, a)
            if isinstance(attr, uv_property):
                if not attr.required:
                    extra_list.append(a)
        for a in extra_list:
            yield a

    def baseline_to_antnums(self, baseline):
        if self.Nants > 2048:
            raise StandardError('error Nants={Nants}>2048 not ' +
                                'supported'.format(Nants=self.Nants))
        if np.min(baseline) > 2**16:
            i = (baseline - 2**16) % 2048 - 1
            j = (baseline - 2**16 - (i+1))/2048 - 1
        else:
            i = (baseline) % 256 - 1
            j = (baseline - (i+1))/256 - 1
        return i, j

    def antnums_to_baseline(self, i, j, attempt256=False):
        # set the attempt256 keyword to True to (try to) use the older
        # 256 standard used in many uvfits files
        # (will use 2048 standard if there are more than 256 antennas)
        if self.Nants > 2048:
            raise StandardError('cannot convert i,j to a baseline index ' +
                                'with Nants={Nants}>2048.'
                                .format(Nants=self.Nants))
        if attempt256 and (np.max(i) < 255 and np.max(j) < 255):
            return 256*(j+1) + (i+1)
        else:
            print('antnums_to_baseline: found > 256 antennas, using ' +
                  '2048 baseline indexing. Beware compatibility with CASA etc')
        return 2048*(j+1)+(i+1)+2**16

    # this needs to exist but doesn't yet
    def ijt_to_blt_index(self, i, j, t):
        self.ant_1_array
        self.ant_2_array
        self.times_array

    def write(self, filename):
        self.check()
        # filename ending in .uvfits gets written as a uvfits
        if filename.endswith('.uvfits'):
            self.write_uvfits(self, filename)

    def read(self, filename, file_type):
        """
        General read function which calls file_type specific read functions
        Inputs:
            filename: string or list of strings
                May be a file name, directory name or a list of file names
                depending on file_type
            file_type: string
                Must be a supported type, see self.supported_file_types
        """
        if file_type not in self.supported_file_types:
            raise ValueError('file_type must be one of ' +
                             ' '.join(self.supported_file_types))
        if file_type == '.uvfits':
            self.read_uvfits(self, filename)
        elif file_type == 'miriad':
            self.read_miriad(self, filename)
        elif file_type == 'fhd':
            self.read_fhd(self, filename)
        self.check()

    def check(self):
        # loop through all required attributes, make sure that they are filled
        attributes = [i for i in self.uv_object.__dict__.keys() if i[0] != '_']
        return True

    def _gethduaxis(self, D, axis):
        ax = str(axis)
        N = D.header['NAXIS'+ax]
        X0 = D.header['CRVAL'+ax]
        dX = D.header['CDELT'+ax]
        Xi0 = D.header['CRPIX'+ax]-1
        return np.arange(X0-dX*Xi0, X0-dX*Xi0+N*dX, dX)

    def _indexhdus(self, hdulist):
        # input a list of hdus
        # return a dictionary of table names
        tablenames = {}
        for i in xrange(len(hdulist)):
            try:
                tablenames[hdulist[i].header['EXTNAME']] = i
            except(KeyError):
                continue
        return tablenames

    def read_uvfits(self, filename):

        F = fits.open(filename)
        D = F[0]  # assumes the visibilities are in the primary hdu
        hdunames = self._indexhdus(F)  # find the rest of the tables
        # check that we have a single source file!! (TODO)

        # astropy.io fits reader scales date according to relevant PZER0 (?)
        self.time_array.value = D.data.field('DATE')

        self.baseline_array.value = D.data.field('BASELINE')

        # check if we have an spw dimension
        if D.header['NAXIS'] == 7:
            if D.header['NAXIS5'] > 1:
                raise(IOError, """Sorry.  Files with more than one spectral
                      window (spw) are not yet supported. A great
                      project for the interested student!""")
            self.Nspws.value = D.header['NAXIS5']
            self.data_array.value = (D.data.field('DATA')[:, 0, 0, :, :, :, 0] +
                               1j * D.data.field('DATA')[:, 0, 0, :, :, :, 1])
            self.flag_array.value = (D.data.field('DATA')[:, 0, 0, :, :, :, 2] <= 0)
            self.nsample_array.value = np.abs(D.data.field('DATA')
                                        [:, 0, 0, :, :, :, 2])
            self.Nspws.value = D.header['NAXIS5']
            assert(self.Nspws.value == self.data_array.value.shape[1])

            # the axis number for phase center depends on if the spw exists
            self.spw_array.value = self._gethduaxis(D, 5)

            self.phase_center_ra.value = D.header['CRVAL6']
            self.phase_center_dec.value = D.header['CRVAL7']
        else:
            # in many uvfits files the spw axis is left out,
            # here we put it back in so the dimensionality stays the same
            self.data_array.value = (D.data.field('DATA')[:, 0, 0, :, :, 0] +
                               1j * D.data.field('DATA')[:, 0, 0, :, :, 1])
            self.data_array.value = self.data_array.value[:, np.newaxis, :, :]
            self.flag_array.value = (D.data.field('DATA')[:, 0, 0, :, :, 2] <= 0)
            self.flag_array.value = self.flag_array.value[:, np.newaxis, :, :]
            self.nsample_array.value = np.abs(D.data.field('DATA')[:, 0, 0, :, :, 2])
            self.nsample_array.value = self.nsample_array.value[:, np.newaxis, :, :]

            # the axis number for phase center depends on if the spw exists
            self.Nspws.value = 1

            self.phase_center_ra.value = D.header['CRVAL5']
            self.phase_center_dec.value = D.header['CRVAL6']

        # get dimension sizes
        self.Nfreqs.value = D.header['NAXIS4']
        assert(self.Nfreqs.value == self.data_array.value.shape[2])
        self.Npols.value = D.header['NAXIS3']
        assert(self.Npols.value == self.data_array.value.shape[3])
        self.Nblts.value = D.header['GCOUNT']
        assert(self.Nblts.value == self.data_array.value.shape[0])

        # read baseline vectors in units of seconds, return in meters
        self.uvw_array.value = (np.array(zip(D.data.field('UU'),
                                         D.data.field('VV'),
                                         D.data.field('WW'))) *
                                const.c.to('m/s').value).T

        self.freq_array.value = self._gethduaxis(D, 4)
        # TODO iterate over the spw axis, for now we just have one spw
        self.freq_array.value.shape = (1,)+self.freq_array.value.shape

        self.polarization_array.value = self._gethduaxis(D, 3)

        # other info -- not required but frequently used
        self.object_name.value = D.header.get('OBJECT', None)
        self.telescope_name.value = D.header.get('TELESCOP', None)
        self.instrument.value = D.header.get('INSTRUME', None)
        self.latitude.value = D.header.get('LAT', None)
        self.longitude.value = D.header.get('LON', None)
        self.altitude.value = D.header.get('ALT', None)
        self.dateobs.value = D.header.get('DATE-OBS', None)
        self.history.value = str(D.header.get('HISTORY', ''))
        self.vis_units.value = D.header.get('BUNIT', None)
        self.phase_center_epoch.value = D.header.get('EPOCH', None)

        # find all the header items after the history and keep them as a dict
        etcpointer = 0
        for thing in D.header:
            etcpointer += 1
            if thing == 'HISTORY':
                break
        for key in D.header[etcpointer:]:
            if key == '':
                continue
            self.extra_keywords.value[key] = D.header[key]

        # READ the antenna table
        # TODO FINISH & test
        ant_hdu = F[hdunames['AIPS AN']]

        # stuff in columns
        self.antenna_names.value = ant_hdu.data.field('ANNAME')
        self.antenna_indices.value = ant_hdu.data.field('NOSTA')
        self.antenna_positions.value = ant_hdu.data.field('STABXYZ')

        # stuff in the header
        if self.telescope_name.value is None:
            self.telescope_name.value = ant_hdu.header['ARRNAM']
        self.xyz_telescope_frame.value = ant_hdu.header['FRAME']
        self.x_telescope.value = ant_hdu.header['ARRAYX']
        self.y_telescope.value = ant_hdu.header['ARRAYY']
        self.z_telescope.value = ant_hdu.header['ARRAYZ']
        self.GST0.value = ant_hdu.header['GSTIA0']
        self.RDate.value = ant_hdu.header['RDATE']
        self.earth_omega.value = ant_hdu.header['DEGPDY']
        self.DUT1.value = ant_hdu.header['UT1UTC']
        try:
            self.TIMESYS.value = ant_hdu.header['TIMESYS']
        except(KeyError):
            # CASA misspells this one
            self.TIMESYS.value = ant_hdu.header['TIMSYS']

        # initialize internal variables based on the antenna table
        self.Nants.value = len(self.antenna_indices.value)
        self.ant_1_array.value, self.ant_2_array.value = \
            self.baseline_to_antnums(self.baseline_array.value)
        del(D)
        return True

    def write_uvfits(self, filename, spoof_nonessential=False):

        for p in self.extra_property_iter():
            prop = getattr(self, p)
            if prop in self.uvfits_required_extra:
                if prop.value is None:
                    if spoof_nonessential:
                        # spoof extra keywords required for uvfits
                        prop.apply_spoof(self)
                        setattr(self, p, prop)
                    else:
                        raise ValueError('Required attribute {attribute} ' +
                                         'for uvfits not defined. Define or ' +
                                         'set spoof_nonessential to True to ' +
                                         'spoof this attribute.'
                                         .format(attribute=attribute_key))

        # TODO document the uvfits weights convention on wiki
        weights_array = self.nsample_array.value * \
            np.where(self.flag_array.value, -1, 1)
        data_array = self.data_array.value[:, np.newaxis, np.newaxis, :, :, :,
                                           np.newaxis]
        weights_array = weights_array[:, np.newaxis, np.newaxis, :, :, :,
                                      np.newaxis]
        # uvfits_array_data shape will be  (Nblts,1,1,[Nspws],Nfreqs,Npols,3)
        print "data_array.shape", data_array.shape
        uvfits_array_data = np.concatenate([data_array.real,
                                           data_array.imag,
                                           weights_array], axis=6)

        uvw_array_sec = self.uvw_array.value / const.c.to('m/s').value
        jd_midnight = np.floor(self.time_array.value[0]-0.5)+0.5

        # uvfits convention is that time_array + jd_midnight = actual JD
        # jd_midnight is julian midnight on first day of observation
        time_array = self.time_array.value - jd_midnight

        ants = self.baseline_to_antnums(self.baseline_array.value)
        baselines_use = self.antnums_to_baseline(ants[0], ants[1],
                                                 attempt256=True)

        # list contains arrays of [u,v,w,date,baseline];
        # each array has shape (Nblts)
        print "uvw_array_sec.shape = ", uvw_array_sec.shape
        print "self.baseline_array.shape = ", self.baseline_array.value.shape
        print "time_array.shape = ", time_array.shape
        group_parameter_list = [uvw_array_sec[0], uvw_array_sec[1],
                                uvw_array_sec[2], time_array,
                                baselines_use]

        hdu = fits.GroupData(uvfits_array_data,
                             parnames=['UU      ', 'VV      ', 'WW      ',
                                       'DATE    ', 'BASELINE'],
                             pardata=group_parameter_list, bitpix=-32)
        hdu = fits.GroupsHDU(hdu)

        # hdu.header['PTYPE1  '] = 'UU      '
        hdu.header['PSCAL1  '] = 1.0
        hdu.header['PZERO1  '] = 0.0

        # hdu.header['PTYPE2  '] = 'VV      '
        hdu.header['PSCAL2  '] = 1.0
        hdu.header['PZERO2  '] = 0.0

        # hdu.header['PTYPE3  '] = 'WW      '
        hdu.header['PSCAL3  '] = 1.0
        hdu.header['PZERO3  '] = 0.0

        # hdu.header['PTYPE4  '] = 'DATE    '
        hdu.header['PSCAL4  '] = 1.0
        hdu.header['PZERO4  '] = jd_midnight

        # hdu.header['PTYPE5  '] = 'BASELINE'
        hdu.header['PSCAL5  '] = 1.0
        hdu.header['PZERO5  '] = 0.0

        # ISO string of first time in self.time_array
        hdu.header['DATE-OBS'] = Time(self.time_array.value[0], scale='utc',
                                      format='jd').iso

        hdu.header['CTYPE2  '] = 'COMPLEX '
        hdu.header['CRVAL2  '] = 1.0
        hdu.header['CRPIX2  '] = 1.0
        hdu.header['CDELT2  '] = 1.0

        hdu.header['CTYPE3  '] = 'STOKES  '
        hdu.header['CRVAL3  '] = self.polarization_array.value[0]
        hdu.header['CRPIX3  '] = 1.0
        try:
            hdu.header['CDELT3  '] = np.diff(self.polarization_array.value)[0]
        except(IndexError):
            hdu.header['CDELT3  '] = 1.0

        hdu.header['CTYPE4  '] = 'FREQ    '
        hdu.header['CRVAL4  '] = self.freq_array.value[0, 0]
        hdu.header['CRPIX4  '] = 1.0
        hdu.header['CDELT4  '] = np.diff(self.freq_array.value[0])[0]

        hdu.header['CTYPE5  '] = 'IF      '
        hdu.header['CRVAL5  '] = 1.0
        hdu.header['CRPIX5  '] = 1.0
        hdu.header['CDELT5  '] = 1.0

        hdu.header['CTYPE6  '] = 'RA'
        hdu.header['CRVAL6  '] = self.phase_center_ra.value

        hdu.header['CTYPE7  '] = 'DEC'
        hdu.header['CRVAL7  '] = self.phase_center_dec.value

        hdu.header['BUNIT   '] = self.vis_units.value
        hdu.header['BSCALE  '] = 1.0
        hdu.header['BZERO   '] = 0.0

        hdu.header['OBJECT  '] = self.object_name.value
        hdu.header['TELESCOP'] = self.telescope_name.value
        hdu.header['LAT     '] = self.latitude.value
        hdu.header['LON     '] = self.longitude.value
        hdu.header['ALT     '] = self.altitude.value
        hdu.header['INSTRUME'] = self.instrument.value
        hdu.header['EPOCH   '] = float(self.phase_center_epoch.value)

        hdu.header['HISTORY '] = self.history.value

        # end standard keywords; begin user-defined keywords
        print "self.extra_keywords = "
        print self.extra_keywords.value
        for key, value in self.extra_keywords.value.iteritems():
            # header keywords have to be 8 characters or less
            keyword = key[:8].upper()
            print "keyword=-value-", keyword+'='+'-'+str(value)+'-'
            hdu.header[keyword] = value

        # ADD the ANTENNA table
        staxof = [0] * self.Nants.value

        # 0 specifies alt-az, 6 would specify a phased array
        mntsta = [0] * self.Nants.value

        poltya = ['X'] * self.Nants.value  # beware, X can mean just about anything
        polaa = [90.0] * self.Nants.value
        poltyb = ['Y'] * self.Nants.value
        polab = [0.0] * self.Nants.value

        col1 = fits.Column(name='ANNAME', format='8A',
                           array=self.antenna_names.value)
        col2 = fits.Column(name='STABXYZ', format='3D',
                           array=self.antenna_positions.value)
        col3 = fits.Column(name='NOSTA', format='1J',
                           array=self.antenna_indices.value)
        col4 = fits.Column(name='MNTSTA', format='1J', array=mntsta)
        col5 = fits.Column(name='STAXOF', format='1E', array=staxof)
        col6 = fits.Column(name='POLTYA', format='1A', array=poltya)
        col7 = fits.Column(name='POLAA', format='1E', array=polaa)
        # col8 = fits.Column(name='POLCALA', format='3E', array=polcala)
        col9 = fits.Column(name='POLTYB', format='1A', array=poltyb)
        col10 = fits.Column(name='POLAB', format='1E', array=polab)
        # col11 = fits.Column(name='POLCALB', format='3E', array=polcalb)
        # note ORBPARM is technically required, but we didn't put it in

        cols = fits.ColDefs([col1, col2, col3, col4, col5, col6, col7, col9,
                             col10])

        # This only works for astropy 0.4 which is not available from pip
        ant_hdu = fits.BinTableHDU.from_columns(cols)

        ant_hdu.header['EXTNAME'] = 'AIPS AN'
        ant_hdu.header['EXTVER'] = 1

        ant_hdu.header['ARRAYX'] = self.x_telescope.value
        ant_hdu.header['ARRAYY'] = self.y_telescope.value
        ant_hdu.header['ARRAYZ'] = self.z_telescope.value
        ant_hdu.header['FRAME'] = self.xyz_telescope_frame.value
        ant_hdu.header['GSTIA0'] = self.GST0.value
        ant_hdu.header['FREQ'] = self.freq_array.value[0, 0]
        ant_hdu.header['RDATE'] = self.RDate.value
        ant_hdu.header['UT1UTC'] = self.DUT1.value

        ant_hdu.header['TIMSYS'] = self.TIMESYS.value
        if self.TIMESYS == 'IAT':
                print "WARNING: FILES WITH TIME SYSTEM 'IAT' ARE NOT SUPPORTED"
        ant_hdu.header['ARRNAM'] = self.telescope_name.value
        ant_hdu.header['NO_IF'] = self.Nspws.value
        ant_hdu.header['DEGPDY'] = self.earth_omega.value
        # ant_hdu.header['IATUTC'] = 35.

        # set mandatory parameters which are not supported by this object
        # (or that we just don't understand)
        ant_hdu.header['NUMORB'] = 0

        # note: Bart had this set to 3. We've set it 0 after aips 117. -jph
        ant_hdu.header['NOPCAL'] = 0

        ant_hdu.header['POLTYPE'] = 'X-Y LIN'

        # note: we do not support the concept of "frequency setups"
        # -- lists of spws given in a SU table.
        ant_hdu.header['FREQID'] = -1

        # if there are offsets in images, this could be the culprit
        ant_hdu.header['POLARX'] = 0.0
        ant_hdu.header['POLARY'] = 0.0

        ant_hdu.header['DATUTC'] = 0  # ONLY UTC SUPPORTED

        # we always output right handed coordinates
        ant_hdu.header['XYZHAND'] = 'RIGHT'

        # ADD the FQ table
        # skipping for now and limiting to a single spw

        # write the file
        hdulist = fits.HDUList(hdus=[hdu, ant_hdu])
        hdulist.writeto(filename, clobber=True)

        return True

    def read_fhd(self, filelist):
        """
        Read in fhd visibility save files
            filelist: list
                list of files containing fhd-style visibility data.
                Must include at least one polarization file, a params file and
                a flag file.
        """

        datafiles = {}
        params_file = None
        flags_file = None
        settings_file = None
        for file in filelist:
            print(file)
            if file.lower().endswith('_vis_xx.sav'):
                datafiles['xx'] = xx_datafile = file
            elif file.lower().endswith('_vis_yy.sav'):
                datafiles['yy'] = yy_datafile = file
            elif file.lower().endswith('_vis_xy.sav'):
                datafiles['xy'] = xy_datafile = file
            elif file.lower().endswith('_vis_yx.sav'):
                datafiles['yx'] = yx_datafile = file
            elif file.lower().endswith('_params.sav'):
                params_file = file
            elif file.lower().endswith('_flags.sav'):
                flags_file = file
            elif file.lower().endswith('_settings.txt'):
                settings_file = file
            else:
                print(file + ' is not a recognized fhd file type')

        if len(datafiles) < 1:
            raise StandardError('No data files included in file list')
        if params_file is None:
            raise StandardError('No params file included in file list')
        if flags_file is None:
            raise StandardError('No flags file included in file list')
        if settings_file is None:
            warnings.warn('No flags file included in file list')

        # TODO: add checking to make sure params, flags and datafiles are
        # consistent with each other

        vis_data = {}
        for pol, file in datafiles.iteritems():
            this_dict = readsav(file, python_dict=True)
            vis_data[pol] = this_dict['vis_ptr']
            this_obs = pd.DataFrame(this_dict['obs'])

        obs = this_obs
        bl_info = pd.DataFrame(obs['BASELINE_INFO'][0])
        meta_data = pd.DataFrame(obs['META_DATA'][0])
        astrometry = pd.DataFrame(obs['ASTR'][0])
        fhd_pol_list = []
        for pol in obs['POL_NAMES'][0]:
            fhd_pol_list.append(pol.decode("utf-8").lower())

        params_dict = readsav(params_file, python_dict=True)
        params = pd.DataFrame(params_dict['params'])

        flags_dict = readsav(flags_file, python_dict=True)
        flag_data = {}
        for index, f in enumerate(flags_dict['flag_arr']):
            flag_data[fhd_pol_list[index]] = f

        self.Ntimes.value = obs['N_TIME'][0]
        self.Nbls.value = obs['NBASELINES'][0]
        self.Nblts.value = self.Ntimes * self.Nbls
        self.Nfreqs.value = obs['N_FREQ'][0]
        self.Npols.value = len(vis_data.keys())
        self.Nspws.value = 1
        self.spw_array.value = [1]
        self.vis_units.value = 'JY'

        lin_pol_order = ['xx', 'yy', 'xy', 'yx']
        linear_pol_dict = dict(zip(lin_pol_order, np.arange(5, 9)*-1))
        pol_list = []
        for pol in lin_pol_order:
            if pol in vis_data:
                pol_list.append(linear_pol_dict[pol])
        self.polarization_array.value = np.asarray(pol_list)

        self.data_array.value = np.zeros((self.Nblts, self.Nspws, self.Nfreqs,
                                          self.Npols), dtype=np.complex_)
        self.nsample_array.value = np.zeros((self.Nblts, self.Nspws,
                                             self.Nfreqs, self.Npols),
                                            dtype=np.float_)
        self.flag_array.value = np.zeros((self.Nblts, self.Nspws, self.Nfreqs,
                                          self.Npols), dtype=np.bool_)
        for pol, vis in vis_data.iteritems():
            pol_i = pol_list.index(linear_pol_dict[pol])
            self.data_array.value[:, 0, :, pol_i] = vis
            self.flag_array.value[:, 0, :, pol_i] = flag_data[pol] <= 0
            self.nsample_array.value[:, 0, :, pol_i] = np.abs(flag_data[pol])

        self.uvw_array.value = np.zeros((3, self.Nblts))
        self.uvw_array.value[0, :] = params['UU'][0]
        self.uvw_array.value[1, :] = params['VV'][0]
        self.uvw_array.value[2, :] = params['WW'][0]

        # bl_info.JDATE (a vector of length Ntimes) is the only safe date/time
        # to use in FHD files.
        # (obs.JD0 (float) and params.TIME (vector of length Nblts) are
        #   context dependent and are not safe
        #   because they depend on the phasing of the visibilities)
        # the values in bl_info.JDATE are the JD for each integration.
        # We need to expand up to Nblts.
        int_times = bl_info['JDATE'][0]
        self.time_array.value = np.zeros(self.Nblts.value)
        for ii in range(0, self.Ntimes.value):
            self.time_array.value[ii*self.Nbls.value:(ii+1)*self.Nbls.value] = int_times[ii]

        self.ant_1_array.value = bl_info['TILE_A'][0]
        self.ant_2_array.value = bl_info['TILE_B'][0]

        self.Nants.value = max([max(self.ant_1_array.value),
                                max(self.ant_2_array.value)])
        self.antenna_names.value = bl_info['TILE_NAMES'][0].tolist()
        self.antenna_indices.value = np.arange(self.Nants.value)

        self.baseline_array.value = self.antnums_to_baseline(self.ant_1_array.value,
                                                             self.ant_2_array.value)

        self.freq_array.value = np.zeros((self.Nspws.value, self.Nfreqs.value),
                                   dtype=np.float_)
        self.freq_array.value[0, :] = bl_info['FREQ'][0]

        if not np.isclose(obs['OBSRA'][0], obs['PHASERA'][0]) or \
                not np.isclose(obs['OBSDEC'][0], obs['PHASEDEC'][0]):
            warnings.warn('These visibilities may have been phased ' +
                          'improperly -- without changing the uvw locations')

        self.phase_center_ra.value = obs['OBSRA'][0]
        self.phase_center_dec.value = obs['OBSDEC'][0]

        # this is generated in FHD by subtracting the JD of neighboring
        # integrations. This can have limited accuracy, so it can be slightly
        # off the actual value.
        # (e.g. 1.999426... rather than 2)
        self.integration_time.value = obs['TIME_RES'][0]
        self.channel_width.value = obs['FREQ_RES'][0]

        # # --- observation information ---
        self.telescope_name.value = obs['INSTRUMENT'][0].decode("utf-8")

        # This is a bit of a kludge because nothing like object_name exists
        # in FHD files.
        # At least for the MWA, obs.ORIG_PHASERA and obs.ORIG_PHASEDEC specify
        # the field the telescope was nominally pointing at
        # (May need to be revisited, but probably isn't too important)
        object_name = 'Field RA(deg): ' + str(obs['ORIG_PHASERA'][0]) + \
                      ', Dec:' + str(obs['ORIG_PHASEDEC'][0])
        # For the MWA, this can sometimes be converted to EoR fields
        if self.telescope_name.value.lower() == 'mwa':
            if np.isclose(obs['ORIG_PHASERA'][0], 0) and \
                    np.isclose(obs['ORIG_PHASEDEC'][0], -27):
                object_name = 'EoR 0 Field'

        self.instrument.value = self.telescope_name.value
        self.latitude.value = obs['LAT'][0]
        self.longitude.value = obs['LON'][0]
        self.altitude.value = obs['ALT'][0]

        # Use the first integration time here
        self.dateobs.value = min(self.time_array.value)

        # history: add the first few lines from the settings file
        if settings_file is not None:
            history_list = ['fhd settings info']
            with open(settings_file) as f:
                head = list(islice(f, 11))
            for line in head:
                newline = ' '.join(str.split(line))
                if not line.startswith('##'):
                    history_list.append(newline)
            self.history.value = '    '.join(history_list)

        self.phase_center_epoch.value = astrometry['EQUINOX'][0]

        # TODO figure out how to calculate the following from what is in the
        # metafits (and passed along by FHD)
        # # coordinate frame for antenna positions (eg 'ITRF'-also google ECEF)
        # # NB: ECEF has x running through long=0 and z through the north pole
        # 'xyz_telescope_frame'  : None,
        # # coordinates of array center in meters in coordinate frame
        # 'x_telescope'  : None,
        # 'y_telescope'  : None,
        # 'z_telescope'  : None,
        # # array giving coordinates of antennas relative to
        # # {x,y,z}_telescope in the same frame, (Nants,3)
        # 'antenna_positions'  : None,

        # # --- other stuff ---
        # # the below are copied from AIPS memo 117, but could be revised to
        # # merge with other sources of data.
        # # when available they are populated. user beware?
        # # Greenwich sidereal time at midnight on reference date
        # 'GST0'  : None,
        # 'RDate'  : None,  # date for which the GST0 or whatever... applies
        # # earth's rotation rate in degrees per day
        # # (might not be enough sigfigs)
        # 'earth_omega'  : 360.985,
        # 'DUT1'  : 0.0,        # DUT1 (google it) AIPS 117 calls it UT1UTC
        # 'TIMESYS'  : 'UTC',   # We only support UTC

        return True

    def read_miriad(self, filepath, FLEXIBLE_OPTION=True):
        # map uvdata attributes to miriad data values
        # those which we can get directly from the miriad file
        # (some, like n_times, have to be calculated)
        miriad_header_data = {'Nfreqs': 'nchan',
                              'Npols': 'npol',
                              'Nspws': 'nspec',  # not always available
                              'phase_center_ra': 'ra',
                              'phase_center_dec': 'dec',
                              'integration_time': 'inttime',
                              'channel_width': 'sdf',  # in Ghz!
                              'object_name': 'source',
                              'telescope_name': 'telescop',
                              'latitude': 'latitud',
                              'longitude': 'longitu',  # in units of radians
                              'dateobs': 'time',  # (get the first time in the ever changing header)
                              'history': 'history',
                              'phase_center_epoch': 'epoch',
                              'Nants': 'nants',
                              'antenna_positions': 'antpos',  # take deltas


                              }
        # things not in the miriad header (but calculable from header)
        # {x,y,z}_telescope
        # spw_array
        # freq_array

        # things we need to get from scanning through the miriad file
        # Ntimes
        # Nbls
        # Nblts
        # data_array
        # uvws  #will we support variable variations?
        # n_sample_array
        # flag_array
        # baseline_array
        # time_array
        # polarization_array
        # ant_1_array
        # ant_2_array
        ant_1_array = []
        ant_2_array = []
        pols = []
        data_accumulator = {}
        flag_accumulator = {}
        for (uvw, t, (i, j)), d, f in uv.all(raw=True):
            # control for the case of only a single spw not showing up in
            # the dimension
            if len(d.shape) == 1:
                d.shape = (1,) + d.shape
            try:
                data_accumulator[uv['pol']].append([uvw, t, i, j, d, f])
            except(KeyError):
                data_accumulator[uv['pol']] = [uvw, t, i, j, d, f]
                # NB: flag types in miriad are usually ints
        self.polarization_array.value = np.sort(data_accumulator.keys())

        if FLEXIBLE_OPTION:
            # get all the unique list of all times ever listed in the file
            times = list(set([[k[1] for k in d] for d in data_accumulator]))
            times = np.sort(times)
            bls = list(set([[(k[2], k[3]) for k in d] for d in data_accumulator]))
            blts = []
            for t in times:
                for bl in bls:
                    blts.append((t, bl))
            # set the data sizes
            self.Nblts.value = len(blts)
            self.Nbls.value = len(bls)
            self.Ntimes.value = len(times)
            assert(self.Nblts.value == self.Nbls.value*self.Ntimes.value)

            # slot the data into a grid
            data_array = np.zeros((Nblts, Nspws, Nfreqs, Npols))
            flag_array = np.zeros((Nblts, Nspws, Nfreqs, Npols))
            for pol, data in data_accumulator.iteritems():
                # search for the correct blt position
                for iblt, blt in enumerate(blts):
                    # TBD: this could be a source of slowness for large datasets
                    if data[1] == blt[0] and (data[2], data[3]) == blt[1]:
                        break
                ipol = np.argwhere(self.polarization_array.value == pol)
                # requires data to have dimension nspec,nfreq
                # for the time being we'll set nspec=1
                data_array[iblt, :, :, ipol] = data[4]
                flag_array[iblt, :, :, ipol] = data[5]

        if not FLEXIBLE_OPTION:
            pass
            # this option would accumulate things requiring
            # baselines and times are sorted in the same
            #          order for each polarization
            # and that there are the same number of baselines
            #          and pols per timestep
            # TBD impliment

        # NOTES:
        # pyuvdata is natively 0 indexed as is miriad
        # miriad uses the same pol2num standard as aips/casa

        # things not in miriad files
        # vis_units

        # things that might not be required?
        # 'GST0'  : None,
        # 'RDate'  : None,  # date for which the GST0 or whatever... applies
        # 'earth_omega'  : 360.985,
        # 'DUT1'  : 0.0,        # DUT1 (google it) AIPS 117 calls it UT1UTC
        # 'TIMESYS'  : 'UTC',   # We only support UTC

        #

        # Phasing rule: if alt/az is set and ra/dec  are None, then its a drift scan

        return True
