# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2018 Radio Astronomy Software Group
# Licensed under the 2-clause BSD License

"""Tests for telescope objects and functions.

"""
import os

import numpy as np
import pytest
from astropy.coordinates import EarthLocation

import pyuvdata
from pyuvdata import Telescope, UVData
from pyuvdata.data import DATA_PATH

required_parameters = ["_name", "_location"]
required_properties = ["name", "location"]
extra_parameters = [
    "_antenna_diameters",
    "_Nants",
    "_antenna_names",
    "_antenna_numbers",
    "_antenna_positions",
    "_x_orientation",
    "_instrument",
]
extra_properties = [
    "antenna_diameters",
    "Nants",
    "antenna_names",
    "antenna_numbers",
    "antenna_positions",
    "x_orientation",
    "instrument",
]
other_attributes = [
    "citation",
    "telescope_location_lat_lon_alt",
    "telescope_location_lat_lon_alt_degrees",
    "pyuvdata_version_str",
]
astropy_sites = EarthLocation.get_site_names()
while "" in astropy_sites:
    astropy_sites.remove("")

# Using set here is a quick way to drop duplicate entries
expected_known_telescopes = list(
    set(astropy_sites + ["PAPER", "HERA", "SMA", "SZA", "OVRO-LWA"])
)


# Tests for Telescope object
def test_parameter_iter():
    "Test expected parameters."
    telescope_obj = pyuvdata.Telescope()
    all_params = []
    for prop in telescope_obj:
        all_params.append(prop)
    for a in required_parameters:
        assert a in all_params, (
            "expected attribute " + a + " not returned in object iterator"
        )


def test_required_parameter_iter():
    "Test expected required parameters."
    telescope_obj = pyuvdata.Telescope()
    required = []
    for prop in telescope_obj.required():
        required.append(prop)
    for a in required_parameters:
        assert a in required, (
            "expected attribute " + a + " not returned in required iterator"
        )


def test_extra_parameter_iter():
    "Test expected optional parameters."
    telescope_obj = pyuvdata.Telescope()
    extra = []
    for prop in telescope_obj.extra():
        extra.append(prop)
    for a in extra_parameters:
        assert a in extra, "expected attribute " + a + " not returned in extra iterator"


def test_unexpected_parameters():
    "Test for extra parameters."
    telescope_obj = pyuvdata.Telescope()
    expected_parameters = required_parameters + extra_parameters
    attributes = [i for i in list(telescope_obj.__dict__.keys()) if i[0] == "_"]
    for a in attributes:
        assert a in expected_parameters, (
            "unexpected parameter " + a + " found in Telescope"
        )


def test_unexpected_attributes():
    "Test for extra attributes."
    telescope_obj = pyuvdata.Telescope()
    expected_attributes = required_properties + other_attributes
    attributes = [i for i in list(telescope_obj.__dict__.keys()) if i[0] != "_"]
    for a in attributes:
        assert a in expected_attributes, (
            "unexpected attribute " + a + " found in Telescope"
        )


def test_properties():
    "Test that properties can be get and set properly."
    telescope_obj = pyuvdata.Telescope()
    prop_dict = dict(list(zip(required_properties, required_parameters)))
    for k, v in prop_dict.items():
        rand_num = np.random.rand()
        setattr(telescope_obj, k, rand_num)
        this_param = getattr(telescope_obj, v)
        try:
            assert rand_num == this_param.value
        except AssertionError:
            print("setting {prop_name} to a random number failed".format(prop_name=k))
            raise


def test_known_telescopes():
    """Test known_telescopes function returns expected results."""
    assert sorted(pyuvdata.known_telescopes()) == sorted(expected_known_telescopes)


def test_from_known():
    for inst in pyuvdata.known_telescopes():
        telescope_obj = Telescope.from_known_telescopes(inst)
        assert telescope_obj.name == inst


def test_get_telescope_center_xyz():
    ref_xyz = (-2562123.42683, 5094215.40141, -2848728.58869)
    ref_latlonalt = (-26.7 * np.pi / 180.0, 116.7 * np.pi / 180.0, 377.8)
    test_telescope_dict = {
        "test": {
            "center_xyz": ref_xyz,
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "citation": "",
        },
        "test2": {
            "center_xyz": ref_xyz,
            "latitude": ref_latlonalt[0],
            "longitude": ref_latlonalt[1],
            "altitude": ref_latlonalt[2],
            "citation": "",
        },
    }
    telescope_obj = Telescope.from_known_telescopes(
        "test", known_telescope_dict=test_telescope_dict
    )
    telescope_obj_ext = Telescope()
    telescope_obj_ext.citation = ""
    telescope_obj_ext.name = "test"
    telescope_obj_ext.location = EarthLocation(*ref_xyz, unit="m")

    assert telescope_obj == telescope_obj_ext

    telescope_obj_ext.name = "test2"
    telescope_obj2 = Telescope.from_known_telescopes(
        "test2", known_telescope_dict=test_telescope_dict
    )
    assert telescope_obj2 == telescope_obj_ext


def test_get_telescope_no_loc():
    test_telescope_dict = {
        "test": {
            "center_xyz": None,
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "citation": "",
        }
    }
    with pytest.raises(
        ValueError,
        match="Bad location information in known_telescopes_dict for telescope "
        "test. Either the center_xyz or the latitude, longitude and altitude of "
        "the telescope must be specified.",
    ):
        Telescope.from_known_telescopes(
            "test", known_telescope_dict=test_telescope_dict
        )


def test_hera_loc():
    hera_file = os.path.join(DATA_PATH, "zen.2458098.45361.HH.uvh5_downselected")
    hera_data = UVData()
    hera_data.read(
        hera_file, read_data=False, file_type="uvh5", use_future_array_shapes=True
    )

    telescope_obj = Telescope.from_known_telescopes("HERA")

    assert np.allclose(
        telescope_obj._location.xyz(),
        hera_data.telescope._location.xyz(),
        rtol=hera_data.telescope._location.tols[0],
        atol=hera_data.telescope._location.tols[1],
    )
