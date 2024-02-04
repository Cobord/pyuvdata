# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2024 Radio Astronomy Software Group
# Licensed under the 2-clause BSD License

"""Class for reading MS calibration tables."""

import warnings

import numpy as np
from astropy.time import Time
from docstring_parser import DocstringStyle

from .. import ms_utils
from .. import utils as uvutils
from ..docstrings import copy_replace_short_description
from .uvcal import UVCal

__all__ = ["MSCal"]

no_casa_message = (
    "casacore is not installed but is required for measurement set functionality"
)

casa_present = True
try:
    from casacore import tables
except ImportError as error:  # pragma: no cover
    casa_present = False
    casa_error = error


class MSCal(UVCal):
    """
    Defines an MS-specific subclass of UVCal for reading MS calibration tables.

    This class should not be interacted with directly, instead use the read_ms_cal
    method on the UVCal class.
    """

    @copy_replace_short_description(UVCal.read_ms_cal, style=DocstringStyle.NUMPYDOC)
    def read_ms_cal(
        self,
        filepath,
        *,
        run_check=True,
        check_extra=True,
        run_check_acceptability=True,
        astrometry_library=None,
    ):
        """Read in an MS-formatted gains table."""
        # Use the utility function to verify this actually is an MS file
        ms_utils._ms_utils_call_checks(filepath)

        # Set some initial things from the get go -- no legacy support
        self._set_flex_spw()
        self._set_future_array_shapes()
        self._set_sky()
        self._set_gain()

        self.filename = filepath

        # get the history info from the ms_utils
        try:
            self.history = ms_utils.read_ms_hist(filepath, self.pyuvdata_version_str)
        except FileNotFoundError:
            self.history = self.pyuvdata_version_str

        tb_main = tables.table(filepath, ack=False)
        main_info_dict = tb_main.info()

        # 'Measurement Set' of type for main MS
        if main_info_dict["type"] == "Measurement Set":
            raise ValueError(
                "This seems to be a Measurement Set containing visibilities, "
                "not a calibration table."
            )

        if main_info_dict["subType"] == "G Jones":
            self._set_gain
            # This is a so-called "wideband" gains calibration table, i.e. not bandpass
            self.wide_band = True
            self.cal_type = "gain"
        elif main_info_dict["subType"] == "B Jones":
            self._set_gain
            # This is a bandpass solution
            self.wide_band = False
            self.cal_type = "gain"
        elif main_info_dict["subType"] == "K Jones":
            # This is a delay solution? Need to understand the units...
            self.wide_band = True
            self.cal_type = "delay"
            raise NotImplementedError("No support yet for delay solutions.")
        else:
            warnings.warn(
                "Cannot recognize solution type, treating as wideband gain solutions."
            )
            self.wide_band = True

        main_keywords = tb_main.getkeywords()
        for keyword in ["CASA_Version", "MSName"]:
            if keyword in main_keywords:
                self.extra_keywords[keyword] = main_keywords[keyword]

        # tb_field = tables.table(filepath + "/FIELD", ack=False)

        # open table with antenna location information
        ant_info = ms_utils.read_ms_ant(filepath)
        obs_info = ms_utils.read_ms_obs(filepath)

        self.observer = obs_info["observer"]
        self.telescope_name = obs_info["telescope_name"]
        self._telescope_location.frame = ant_info["telescope_frame"]

        # check to see if a TELESCOPE_LOCATION column is present in the observation
        # table. This is non-standard, but inserted by pyuvdata
        if "telescope_location" in obs_info:
            self.telescope_location = obs_info["telescope_location"]
        else:
            # get it from known telescopes
            try:
                self.set_telescope_params()
            except ValueError:
                # If no telescope is found, the we will set the telescope position to be
                # the mean of the antenna positions (this is not ideal!)
                self.telescope_location = np.mean(ant_info["antenna_positions"], axis=0)

        self.antenna_names = ant_info["antenna_names"]
        self.Nants_telescope = len(self.antenna_names)
        self.antenna_numbers = ant_info["antenna_numbers"]
        self.antenna_diameters = ant_info["antenna_diameters"]
        # MS-format seems to want to preserve the blank entries in the gains tables
        # This looks to be the same for MS files.
        self.ant_array = self.antenna_numbers
        self.Nants_data = self.Nants_telescope

        self.antenna_positions = ant_info["antenna_positions"]
        # Subtract off telescope location to get relative ECEF
        self.antenna_positions -= self.telescope_location.reshape(1, 3)
        self.phase_center_catalog = ms_utils.read_ms_field(
            filepath, return_phase_center_catalog=True
        )

        # importuvfits measurement sets store antenna names in the STATION column.
        # cotter measurement sets store antenna names in the NAME column, which is
        # inline with the MS definition doc. In that case all the station names are
        # the same. Default to using what the MS definition doc specifies, unless
        # we read importuvfits in the history, or if the antenna column is not filled.
        if self.Nants_telescope != len(np.unique(self.antenna_names)) or (
            "" in self.antenna_names
        ):
            self.antenna_names = ant_info["station_names"]

        # Extract out the reference antenna information.
        ref_ant_array = tb_main.getcol("ANTENNA2")
        if not all(ref_ant_array[0] == ref_ant_array):
            warnings.warn(
                "Multiple ref ants detected, which UVCal cannot handle. Using the "
                "first entry as the default"
            )

        self.ref_antenna_name = self.antenna_names[
            np.where(self.antenna_numbers == ref_ant_array[0])[0][0]
        ]

        spw_info = ms_utils.read_ms_spw(filepath)

        self.spw_array = spw_info["assoc_spw_id"]
        self.Nspws = len(self.spw_array)
        self.Nfreqs = sum(spw_info["num_chan"])

        self.freq_array = np.zeros(self.Nfreqs, dtype=float)
        self.channel_width = np.zeros(self.Nfreqs, dtype=float)
        self.flex_spw_id_array = np.zeros(self.Nfreqs, dtype=int)
        spw_slice_dict = {}
        for spw_id, spw_idx, spw_nchan, spw_end_chan, spw_freqs, spw_chan_width in zip(
            self.spw_array,
            spw_info["row_idx"],
            spw_info["num_chan"],
            np.cumsum(spw_info["num_chan"]),
            spw_info["chan_freq"],
            spw_info["chan_width"],
        ):
            spw_slice = slice(spw_end_chan - spw_nchan, spw_end_chan)
            spw_slice_dict[spw_idx] = spw_slice
            self.freq_array[spw_slice] = spw_freqs
            self.channel_width[spw_slice] = spw_chan_width
            self.flex_spw_id_array[spw_slice] = spw_id

        # Don't think CASA is going to support a non-sky based model, but hey, who knows
        self.cal_style = "sky"
        self.gain_convention = "multiply"  # Need to verify this or "divide"
        self.Nsources = len(np.unique(tb_main.getcol("FIELD_ID")))

        # Just assume that the gain scale is always in Jy
        self.gain_scale = "Jy"
        if self.wide_band:
            self.freq_range = np.vstack(
                (
                    self.freq_array - (self.channel_width / 2),
                    self.freq_array + (self.channel_width / 2),
                )
            ).T
        self.sky_catalog = "CASA (import)"

        # MAIN LOOP
        self.Njones = tb_main.getcell("CPARAM", 0).shape[1]
        if main_keywords["PolBasis"].lower() == "unknown":
            warnings.warn(
                "Unknown polarization basis for solutions, jones_array values "
                "may be spurious."
            )
            self.jones_array = np.zeros(self.Njones, dtype=int)
        else:
            raise NotImplementedError("Not sure how to read this file yet...")

        time_dict = {}
        row_timeidx_map = []
        time_count = 0
        for time in tb_main.getcol("TIME"):
            try:
                row_timeidx_map.append(time_dict[time])
            except KeyError:
                # Check to see if there are any nearby entries, accounting for the fact
                # that MS stores times in seconds and time_array tolerances are
                # specified in days.
                close_check = np.isclose(
                    list(time_dict),
                    time,
                    rtol=self._time_array.tols[0] * 86400,
                    atol=self._time_array.tols[1] * 86400,
                )
                if any(close_check):
                    # Fill in the first closest entry matched
                    time_dict[time] = np.where(close_check)[0][0]
                else:
                    # Otherwise, plug in a new entry
                    time_dict[time] = time_count
                    time_count += 1
                # Finally, update the row_map with the correct value
                row_timeidx_map.append(time_dict[time])

        self.time_array = np.zeros(time_count, dtype=float)
        self.integration_time = np.zeros(time_count, dtype=float)
        self.Ntimes = time_count

        # Make a map to things.
        ant_dict = {ant: idx for idx, ant in enumerate(self.antenna_numbers)}
        cal_arr_shape = (self.Nants_data, self.Nfreqs, self.Ntimes, self.Njones)
        ms_cal_soln = np.zeros(cal_arr_shape, dtype=complex)
        self.quality_array = np.zeros(cal_arr_shape, dtype=float)
        self.flag_array = np.ones(cal_arr_shape, dtype=bool)
        self.total_quality_array = None  # Always None for now, no similar array in MS
        self.scan_number_array = np.zeros_like(self.time_array, dtype=int)
        self.phase_center_id_array = np.zeros_like(self.time_array, dtype=int)

        for row_idx, time_idx in enumerate(row_timeidx_map):
            try:
                ant_idx = ant_dict[tb_main.getcell("ANTENNA1", row_idx)]
                time_val = tb_main.getcell("TIME", row_idx)
                cal_soln = tb_main.getcell("CPARAM", row_idx)
                cal_qual = tb_main.getcell("PARAMERR", row_idx)
                cal_flag = tb_main.getcell("FLAG", row_idx)
                field_id = tb_main.getcell("FIELD_ID", row_idx)
                scan_num = tb_main.getcell("SCAN_NUMBER", row_idx)
                int_time = tb_main.getcell("INTERVAL", row_idx)
                spw_id = tb_main.getcell("SPECTRAL_WINDOW_ID", row_idx)

                # Figure out which spectral slice this corresponds to
                spw_slice = spw_slice_dict[spw_id]

                # Finally, start plugging in solns to various parameters.
                ms_cal_soln[ant_idx, spw_slice, time_idx, :] = cal_soln
                self.time_array[time_idx] = time_val
                self.integration_time[time_idx] = int_time
                self.quality_array[ant_idx, spw_slice, time_idx, :] = cal_qual
                self.flag_array[ant_idx, spw_slice, time_idx, :] = cal_flag
                self.phase_center_id_array[time_idx] = field_id
                self.scan_number_array[time_idx] = scan_num
            except KeyError:
                # If there's no entry that matches, it's because we've effectively
                # flagged some index value such that it has no entries in the table.
                # skip recording this row.
                continue

        # Convert the time from MJD secs (CASA standard) to JD date (pyuvdata std)
        self.time_array = Time(
            self.time_array / 86400.0,
            format="mjd",
            scale=ms_utils.read_time_scale(tb_main),
        ).utc.jd

        # There's a little bit of cleanup to do w/ field_id, since the values here
        # correspond to the row in FIELD rather than the source ID. Map that now.
        field_id_map = dict(enumerate(self.phase_center_catalog))
        self.phase_center_id_array = np.array(
            [field_id_map[idx] for idx in self.phase_center_id_array]
        )

        # I think this is always east.
        self.x_orientation = "east"
        # Use if this is a delay soln
        if self.cal_type == "gain":
            self.gain_array = ms_cal_soln
        elif self.cal_type == "delay":
            self.delay_array = ms_cal_soln

        self.set_lsts_from_time_array(astrometry_library=astrometry_library)

        if run_check:
            self.check(
                check_extra=check_extra, run_check_acceptability=run_check_acceptability
            )

    def write_ms_cal(self, filename, clobber=False):
        """Write out a MS calibration table."""
        try:
            ms_utils._ms_utils_call_checks(filename, invert_check=True)
        except FileExistsError as err:
            if not clobber:
                raise FileExistsError(
                    "File already exists, must set clobber=True to proceed."
                ) from err

        # Initialize our calibration file, and get things set up with the appropriate
        # columns for us to write to in the main table.
        ms_utils.init_ms_cal_file(filename)

        # There's a little bit of extra handling required here for the different gains
        # types, which are encoded in the first letter of the subtype name. Best docs
        # for this actually exist from AIPS++ days, which can be found at:
        # https://casa.nrao.edu/aips2_docs/user/SynthesisRef/node27.html#calibrater
        #
        # Short summary here:
        # G == Ant-based, multiplicative complex gains
        #       --> In UVCal terms, wide_band gains
        # B == Ant-based complex bandpass; a frequency-dependent version of G
        # T == Ant-based pol-independent (tropospheric) gain; a pol-indep version of G
        #       --> This basically means Njones is forced to 1
        # D == Ant-based instrumental polarization leakage
        #       --> TODO: Support for this to once I (Karto) understand UVCal pol cal
        # M == Baseline-based complex gains; baseline-based version of G (blech)
        # MF == Baseline-based complex bandpass: baseline-based version of B (2x blech)
        # K == Ant-based delays (above suggests bsl-based, but CASA 6.x says ant-based)
        #       --> TODO: Support for this coming once units are sorted out.

        if self.cal_type == "gain":
            casa_subtype = "G Jones" if self.wide_band else "B Jones"
        else:
            raise NotImplementedError("Sorry, still working on this...")

        with tables.table(filename, ack=False, readonly=False) as ms:
            # Update the top-level info with the correct gains subtype.
            info_dict = ms.info()
            info_dict["subType"] = casa_subtype
            ms.putinfo(info_dict)

            # Update the keywords that we know
            ms.putkeyword("VisCal", casa_subtype)
            if len(self.extra_keywords) != 0:
                extra_copy = self.extra_keywords.copy()
                for key in ("CASA_Version", "MSName"):
                    if key in self.extra_keywords:
                        ms.putkeyword(key, extra_copy.pop(key))
                if len(extra_copy) != 0:
                    ms.putkeyword("pyuvdata_extra", extra_copy)

            if self.x_orientation is not None:
                ms.putkeyword("pyuvdata_xorient", self.x_orientation)

            # Now start the heavy lifting of putting in the data.
            ############################################################################
            # astropy's Time has some overheads associated with it, so use unique to run
            # this date conversion as few times as possible. Note that the default for
            # MS is MJD UTC seconds, versus JD UTC days for UVData.
            time_array, time_ind = np.unique(self.time_array, return_inverse=True)
            time_array = (Time(time_array, format="jd", scale="utc").mjd * 86400.0)[
                time_ind
            ]

            # For some reason, CASA seems to want to pad the main table with zero
            # entries for the "blank" antennas, similar to what's seen in the ANTENNA
            # table. So we'll calculate this up front for convenience.
            Nants_casa = np.max(self.antenna_numbers) + 1

            # Add all the rows we need up front, which will allow us to fill the
            # columns all in one shot.
            ms.addrows(self.Ntimes * self.Nfreqs * Nants_casa)

            # Assume we have _more_ than one spectral window, where each needs to be
            # handled  separately, since they can have differing numbers of channels.
            # (n.b., tables.putvarcol can write complex tables like these, but its
            # slower and more memory-intensive than putcol).
            spw_sel_dict = {}
            for spw_id in self.spw_array:
                spw_selection = self.flex_spw_id_array == spw_id
                spw_nchan = sum(spw_selection)
                [spw_selection], _ = uvutils._convert_to_slices(
                    spw_selection, max_nslice=1, return_index_on_fail=True
                )
                spw_sel_dict[spw_id] = (spw_selection, spw_nchan)

            # Based on some analysis of ALMA/ACA data, various routines in CASA appear
            # to prefer data be grouped together on a "per-scan" basis, then per-spw,
            # and then the more usual selections of per-time, per-ant1, etc.

            ant_array = np.tile(np.arange(Nants_casa), self.Ntimes * self.Nspws)
            refant = self.antenna_numbers[
                self.antenna_names.index(self.ref_antenna_name)
            ]
            refant_array = np.full_like(ant_array, refant)

            # Time-based properties need to be repeated on Nants_casa, since the antenna
            # axis is the "fastest" moving on the collapsed data. So repeat each entry
            # by the number of antennas, before tiling the whole thing by the number of
            # spectral windows (the preferred outer-most axis).
            interval_arr = np.tile(
                np.repeat(self.integration_time, Nants_casa), self.Nspws
            )
            time_array = np.tile(np.repeat(time_array, Nants_casa), self.Nspws)

            # Move on to the time-based optional parameters
            if self.scan_number_array is None:
                scan_number_array = np.zeros_like(time_array, dtype=int)
            else:
                scan_number_array = np.tile(
                    np.repeat(self.scan_number_array, Nants_casa), self.Nspws
                )

            if self.phase_center_id_array is None:
                field_ids = np.zeros_like(time_array, dtype=int)
            else:
                # We have to do an extra bit of work here, as he ID number needs to
                # match to the row number in the FIELD table). We do that by looking at
                # the ordering of phase_center_catalog, which is what's used to write
                # out the FIELD table.
                field_ids = np.zeros_like(self.phase_center_id_array)
                for idx, cat_id in enumerate(self.phase_center_catalog):
                    field_ids[self.phase_center_id_array == cat_id] = idx
                field_ids = np.tile(np.repeat(field_ids, Nants_casa), self.Nspws)

            # spw ids are on the outer most axis, so they just need to be repeated.
            spw_id_array = np.repeat(np.arange(self.Nspws), Nants_casa * self.Ntimes)

            # Set this always to zero for now -- not sure when its needed yet.
            obs_id_array = np.zeros_like(spw_id_array)

            # Calculate the number of times we need to duplicate records b/c of the way
            # that CASA stores information.
            ms.putcol("TIME", time_array)
            ms.putcol("FIELD_ID", field_ids)
            ms.putcol("SPECTRAL_WINDOW_ID", spw_id_array)
            ms.putcol("ANTENNA1", ant_array)
            ms.putcol("ANTENNA2", refant_array)
            ms.putcol("INTERVAL", interval_arr)
            ms.putcol("SCAN_NUMBER", scan_number_array)
            ms.putcol("OBSERVATION_ID", obs_id_array)

            # Alright, all the easy stuff is over, time to move on to the the heavy
            # lifting, which we'll do spectral window by spectral window.
            for count, spw_id in enumerate(self.spw_array):
                # TODO: Change placeholder value
                pol_order = ...
                spw_sel, spw_nchan = spw_sel_dict[spw_id]
                subarr_shape = (self.Ntimes, Nants_casa, spw_nchan, self.Njones)

                qual_arr = np.ones(
                    (self.Nants_data, spw_nchan, self.Ntimes, self.Njones), dtype=float
                )
                if self.quality_array is not None:
                    qual_arr *= self.quality_array[:, spw_sel, :, :]
                if self.total_quality_array is not None:
                    qual_arr *= self.total_quality_array[spw_sel, :, :]

                # We're going to leave a placeholder for SNR for now, since it's
                # somewhat redundant and not totally clear how it's calculated.
                data_dict = {
                    "CPARAM": self.gain_array[:, spw_sel, :, :],
                    "FLAG": self.flag_array[:, spw_sel, :, :],
                    "PARAMERR": qual_arr,
                    "SNR": np.zeros_like(qual_arr),
                }
                # N.b. (Karto): WEIGHT was totally unfilled in every example file that
                # I poked at that was generated via CASA. It iss possible it's not
                # actually used for anything or is otherwise vestigial, so leave it be

                for item in data_dict:
                    subarr = data_dict[item]
                    # data_form = ("Nants_data", "Nfreqs", "Ntimes", "Njones")
                    # Order it so that it goes Ntimes -> Nants -> Nfreqs -> Njones
                    subarr = np.transpose(subarr, [2, 0, 1, 3])

                    # Set zeros by default ()
                    new_subarr = np.zeros(subarr_shape, dtype=subarr.dtype)
                    if item == "FLAG":
                        # Mark all entries flagged by default
                        new_subarr[...] = True

                    # Do a little bit of casting magic to plug in the antenna numbers
                    # that we actualy have (versus the spoofed/padded ones).
                    new_subarr[:, self.ant_array, :, :] = subarr[:, :, :, pol_order]

                    # Finally, get this into a 3D array that we can use in
                    new_subarr = np.reshape(
                        new_subarr, (self.Ntimes * Nants_casa, spw_nchan, self.Njones)
                    )
                    # Plug this pack in to our data dict
                    data_dict[item] = new_subarr

                # Finally, time to plug the valuse into the MS table
                for key in data_dict:
                    ms.putcol(
                        key,
                        data_dict[key],
                        (count * (Nants_casa * self.Ntimes)),
                        (Nants_casa * self.Ntimes),
                    )

        # Alright, main table is done (and because w/ used `with`, already closed).
        # Finally, write all of the supporting tables that we need.
        ms_utils.write_ms_antenna(filename, self)
        if self.phase_center_catalog is None:
            cat_dict = {
                0: {
                    "cat_lat": 0.0,
                    "cat_lon": 0.0,
                    "cat_name": "unknown",
                    "cat_type": "sidereal",
                    "cat_frame": "icrs",
                    "cat_epoch": 2000.0,
                }
            }
            ms_utils.write_ms_field(
                filename, phase_center_catalog=cat_dict, time_val=0.0
            )
        else:
            ms_utils.write_ms_field(filename, self)

        ms_utils.write_ms_history(filename, self.history)
        ms_utils.write_ms_observation(filename, self)
        ms_utils.write_ms_spectral_window(filename, self)
