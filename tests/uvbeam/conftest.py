# Copyright (c) 2021 Radio Astronomy Software Group
# Licensed under the 2-clause BSD License

"""pytest fixtures for UVBeam tests."""

import os

import numpy as np
import pytest

from pyuvdata import UVBeam
from pyuvdata.data import DATA_PATH

filenames = ["HERA_NicCST_150MHz.txt", "HERA_NicCST_123MHz.txt"]
cst_folder = "NicCSTbeams"
cst_files = [os.path.join(DATA_PATH, cst_folder, f) for f in filenames]

# define some values for optional params here so same across efield & power beams
receiver_temperature_array = np.random.normal(50.0, 5, size=2)
loss_array = np.random.normal(50.0, 5, size=2)
mismatch_array = np.random.normal(0.0, 1.0, size=2)
s_parameters = np.random.normal(0.0, 0.3, size=(4, 2))


def make_cst_beam(beam_type):
    """Make the default CST testing beam."""
    extra_keywords = {
        "software": "CST 2016",
        "sim_type": "E-farfield",
        "layout": "1 antenna",
        "port_num": 1,
    }

    beam = UVBeam()
    beam.read_cst_beam(
        cst_files,
        beam_type=beam_type,
        frequency=[150e6, 123e6],
        telescope_name="HERA",
        feed_name="Dipole",
        feed_version="1.0",
        feed_pol=["x"],
        model_name="Dipole - Rigging height 4.9 m",
        model_version="1.0",
        x_orientation="east",
        reference_impedance=100,
        history=(
            "Derived from https://github.com/Nicolas-Fagnoni/Simulations."
            "\nOnly 2 files included to keep test data volume low."
        ),
        extra_keywords=extra_keywords,
    )

    # add optional parameters for testing purposes
    beam.reference_impedance = 340.0
    beam.receiver_temperature_array = receiver_temperature_array
    beam.loss_array = loss_array
    beam.mismatch_array = mismatch_array
    beam.s_parameters = s_parameters

    return beam


def cut_beam(beam):
    """Downselect a beam to a small sky area to speed tests up."""
    za_max = np.deg2rad(10.0)
    za_inds_use = np.nonzero(beam.axis2_array <= za_max)[0]
    beam.select(axis2_inds=za_inds_use)
    return beam


def single_freq_version(beam):
    """Make a single freq version with expected history."""
    history_use = beam.history[: beam.history.find(" Combined data")]
    beam.select(freq_chans=1)
    beam.filename = [beam.filename[1]]
    beam._filename.form = (1,)
    beam.history = history_use
    return beam


@pytest.fixture(scope="session")
def cst_efield_2freq_main():
    """Make session level 2-freq efield beam."""
    beam = make_cst_beam("efield")

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_efield_2freq(cst_efield_2freq_main):
    """Make function level 2-freq efield beam."""
    beam = cst_efield_2freq_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_efield_2freq_cut_main(cst_efield_2freq_main):
    """Make session level cut down 2-freq efield beam."""
    beam = cut_beam(cst_efield_2freq_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_efield_2freq_cut(cst_efield_2freq_cut_main):
    """Make function level cut down 2-freq efield beam."""
    beam = cst_efield_2freq_cut_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_efield_2freq_cut_healpix_main(cst_efield_2freq_cut_main):
    """Make session level cut down HEALPix 2-freq efield beam."""
    pytest.importorskip("astropy_healpix")
    beam = cst_efield_2freq_cut_main.copy()
    beam.to_healpix()

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_efield_2freq_cut_healpix(cst_efield_2freq_cut_healpix_main):
    """Make function level cut down HEALPix 2-freq efield beam."""
    beam = cst_efield_2freq_cut_healpix_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_efield_1freq_main(cst_efield_2freq_main):
    """Make session level single freq efield beam."""
    beam = single_freq_version(cst_efield_2freq_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_efield_1freq(cst_efield_1freq_main):
    """Make function level single freq efield beam."""
    beam = cst_efield_1freq_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_efield_1freq_cut_main(cst_efield_2freq_cut_main):
    """Make session level cut down single freq efield beam."""
    beam = single_freq_version(cst_efield_2freq_cut_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_efield_1freq_cut(cst_efield_1freq_cut_main):
    """Make function level cut down single freq efield beam."""
    beam = cst_efield_1freq_cut_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_efield_1freq_cut_healpix_main(cst_efield_2freq_cut_healpix_main):
    """Make session level HEALPix cut down single freq efield beam."""
    beam = single_freq_version(cst_efield_2freq_cut_healpix_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_efield_1freq_cut_healpix(cst_efield_1freq_cut_healpix_main):
    """Make function level HEALPix cut down single freq efield beam."""
    beam = cst_efield_1freq_cut_healpix_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_power_2freq_main():
    """Make session level 2-freq power beam."""
    beam = make_cst_beam("power")

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_power_2freq(cst_power_2freq_main):
    """Make function level 2-freq efield beam."""
    beam = cst_power_2freq_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_power_2freq_cut_main(cst_power_2freq_main):
    """Make session level cut down 2-freq power beam."""
    beam = cut_beam(cst_power_2freq_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_power_2freq_cut(cst_power_2freq_cut_main):
    """Make function level cut down 2-freq power beam."""
    beam = cst_power_2freq_cut_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_power_2freq_cut_healpix_main(cst_power_2freq_cut_main):
    """Make session level HEALPix cut down 2-freq power beam."""
    pytest.importorskip("astropy_healpix")
    beam = cst_power_2freq_cut_main.copy()
    beam.to_healpix()

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_power_2freq_cut_healpix(cst_power_2freq_cut_healpix_main):
    """Make function level HEALPix cut down 2-freq power beam."""
    beam = cst_power_2freq_cut_healpix_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_power_1freq_main(cst_power_2freq_main):
    """Make session level single freq power beam."""
    beam = single_freq_version(cst_power_2freq_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_power_1freq(cst_power_1freq_main):
    """Make function level single freq power beam."""
    beam = cst_power_1freq_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_power_1freq_cut_main(cst_power_2freq_cut_main):
    """Make session level cut down single freq power beam."""
    beam = single_freq_version(cst_power_2freq_cut_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_power_1freq_cut(cst_power_1freq_cut_main):
    """Make function level cut down single freq power beam."""
    beam = cst_power_1freq_cut_main.copy()

    yield beam
    del beam


@pytest.fixture(scope="session")
def cst_power_1freq_cut_healpix_main(cst_power_2freq_cut_healpix_main):
    """Make session level HEALPix cut down single freq power beam."""
    beam = single_freq_version(cst_power_2freq_cut_healpix_main.copy())

    yield beam
    del beam


@pytest.fixture(scope="function")
def cst_power_1freq_cut_healpix(cst_power_1freq_cut_healpix_main):
    """Make function level HEALPix cut down single freq power beam."""
    beam = cst_power_1freq_cut_healpix_main.copy()

    yield beam
    del beam


@pytest.fixture
def phased_array_beam_2freq(cst_efield_2freq):
    """Basic phased_array beam for testing."""
    beam = cst_efield_2freq.copy()
    beam.antenna_type = "phased_array"
    beam.Nelements = 4
    beam.coupling_matrix = np.zeros(
        (beam.Nelements, beam.Nelements, beam.Nfeeds, beam.Nfeeds, beam.Nfreqs),
        dtype=complex,
    )
    for element in range(beam.Nelements):
        beam.coupling_matrix[element, element] = np.ones(
            (beam.Nfeeds, beam.Nfeeds, beam.Nfreqs)
        )
    beam.delay_array = np.zeros(beam.Nelements, dtype=float)
    beam.gain_array = np.ones(beam.Nelements, dtype=float)
    beam.element_coordinate_system = "x-y"
    element_x_array, element_y_array = np.meshgrid(
        np.arange(2) * 2.5, np.arange(2) * 2.5
    )
    beam.element_location_array = np.concatenate(
        (np.reshape(element_x_array, (1, 4)), np.reshape(element_y_array, (1, 4)))
    )

    beam.check()

    yield beam
    del beam


@pytest.fixture
def phased_array_beam_1freq(phased_array_beam_2freq):
    """Basic phased_array beam for testing."""
    beam = single_freq_version(phased_array_beam_2freq.copy())

    yield beam
    del beam


@pytest.fixture()
def az_za_coords():
    az_array = np.deg2rad(np.linspace(0, 350, 36))
    za_array = np.deg2rad(np.linspace(0, 90, 10))

    return az_array, za_array


@pytest.fixture()
def az_za_deg_grid(az_za_coords):
    az_array, za_array = az_za_coords
    freqs = np.linspace(100, 200, 11) * 1e8

    az_vals, za_vals = np.meshgrid(az_array, za_array)

    return az_vals.flatten(), za_vals.flatten(), freqs


@pytest.fixture()
def xy_grid():
    nfreqs = 20
    freqs = np.linspace(100e6, 130e6, nfreqs)

    xy_half_n = 250
    zmax = np.radians(90)  # Degrees
    arr = np.arange(-xy_half_n, xy_half_n)
    x_arr, y_arr = np.meshgrid(arr, arr)
    x_arr = x_arr.flatten()
    y_arr = y_arr.flatten()
    radius = np.sqrt(x_arr**2 + y_arr**2) / float(xy_half_n)
    za_array = radius * zmax
    az_array = np.arctan2(y_arr, x_arr)

    return az_array, za_array, freqs
