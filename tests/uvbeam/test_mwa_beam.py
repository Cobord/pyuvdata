# Copyright (c) 2019 Radio Astronomy Software Group
# Licensed under the 2-clause BSD License
import os

import numpy as np
import pytest

from pyuvdata import UVBeam, utils
from pyuvdata.data import DATA_PATH
from pyuvdata.testing import check_warnings
from pyuvdata.uvbeam.mwa_beam import P1sin, P1sin_array

filename = os.path.join(DATA_PATH, "mwa_full_EE_test.h5")


@pytest.fixture(scope="module")
def mwa_beam_1ppd_main():
    beam = UVBeam()
    beam.read_mwa_beam(filename, pixels_per_deg=1)

    yield beam
    del beam


@pytest.fixture(scope="function")
def mwa_beam_1ppd(mwa_beam_1ppd_main):
    beam = mwa_beam_1ppd_main.copy()

    yield beam
    del beam


def test_read_write_mwa(mwa_beam_1ppd, tmp_path):
    """Basic read/write test."""
    beam1 = mwa_beam_1ppd
    beam2 = UVBeam()

    beam1.read_mwa_beam(filename, pixels_per_deg=1)
    assert beam1.filename == ["mwa_full_EE_test.h5"]

    assert beam1.pixel_coordinate_system == "az_za"
    assert beam1.beam_type == "efield"
    assert beam1.data_array.shape == (2, 2, 3, 91, 360)

    # this is entirely empirical, just to prevent unexpected changes.
    # The actual values have been validated through external tests against
    # the mwa_pb repo.
    assert np.isclose(
        np.max(np.abs(beam1.data_array)),
        0.6823676193472403,
        rtol=beam1._data_array.tols[0],
        atol=beam1._data_array.tols[1],
    )

    assert "x" in beam1.feed_array
    assert "y" in beam1.feed_array
    assert beam1.x_orientation == "east"

    outfile_name = str(tmp_path / "mwa_beam_out.fits")
    beam1.write_beamfits(outfile_name, clobber=True)

    beam2.read_beamfits(outfile_name)

    assert beam1 == beam2


@pytest.mark.filterwarnings("ignore:There are some terminated dipoles")
def test_mwa_orientation(mwa_beam_1ppd):
    power_beam = mwa_beam_1ppd.efield_to_power(inplace=False)

    za_val = np.nonzero(np.isclose(power_beam.axis2_array, 15.0 * np.pi / 180))

    east_az = np.nonzero(np.isclose(power_beam.axis1_array, 0))
    north_az = np.nonzero(np.isclose(power_beam.axis1_array, np.pi / 2))

    east_ind = np.nonzero(
        power_beam.polarization_array
        == utils.polstr2num("ee", x_orientation=power_beam.x_orientation)
    )
    north_ind = np.nonzero(
        power_beam.polarization_array
        == utils.polstr2num("nn", x_orientation=power_beam.x_orientation)
    )

    # check that the e/w dipole is more sensitive n/s
    assert (
        power_beam.data_array[0, east_ind, 0, za_val, east_az]
        < power_beam.data_array[0, east_ind, 0, za_val, north_az]
    )

    # check that the n/s dipole is more sensitive e/w
    assert (
        power_beam.data_array[0, north_ind, 0, za_val, north_az]
        < power_beam.data_array[0, north_ind, 0, za_val, east_az]
    )

    # check that for a single dipole (all others turned off) there is higher
    # azimuth-aligned response near the horizon than zenith angle-aligned response
    # for both feed orientations
    # this is true with all dipoles on too, but the difference is bigger for a
    # single dipole
    delays = np.full((2, 16), 32, dtype=int)
    delays[:, 5] = 0
    efield_beam = UVBeam.from_file(filename, pixels_per_deg=1, delays=delays)

    za_val = np.nonzero(np.isclose(efield_beam.axis2_array, 80.0 * np.pi / 180))

    max_az_response = np.max(np.abs(efield_beam.data_array[0, east_ind, 0, za_val, :]))
    max_za_response = np.max(np.abs(efield_beam.data_array[1, east_ind, 0, za_val, :]))
    assert max_az_response > max_za_response

    max_az_response = np.max(np.abs(efield_beam.data_array[0, north_ind, 0, za_val, :]))
    max_za_response = np.max(np.abs(efield_beam.data_array[1, north_ind, 0, za_val, :]))
    assert max_az_response > max_za_response


def test_freq_range(mwa_beam_1ppd):
    beam1 = mwa_beam_1ppd
    beam2 = UVBeam()

    # include all
    beam2.read_mwa_beam(filename, pixels_per_deg=1, freq_range=[100e6, 200e6])
    assert beam1 == beam2

    beam2.read_mwa_beam(filename, pixels_per_deg=1, freq_range=[100e6, 150e6])
    beam1.select(freq_chans=[0, 1])
    assert beam1.history != beam2.history
    beam1.history = beam2.history
    assert beam1 == beam2

    with check_warnings(UserWarning, match="Only one available frequency"):
        beam1.read_mwa_beam(filename, pixels_per_deg=1, freq_range=[100e6, 130e6])

    with pytest.raises(ValueError, match="No frequencies available in freq_range"):
        beam2.read_mwa_beam(filename, pixels_per_deg=1, freq_range=[100e6, 110e6])

    with pytest.raises(ValueError, match="freq_range must have 2 elements."):
        beam2.read_mwa_beam(filename, pixels_per_deg=1, freq_range=[100e6])


def test_p1sin_array():
    pixels_per_deg = 5
    nmax = 10
    n_theta = np.floor(90 * pixels_per_deg) + 1
    theta_arr = np.deg2rad(np.arange(0, n_theta) / pixels_per_deg)
    (P_sin, P1) = P1sin_array(nmax, theta_arr)

    P_sin_orig = np.zeros((nmax**2 + 2 * nmax, np.size(theta_arr)))
    P1_orig = np.zeros((nmax**2 + 2 * nmax, np.size(theta_arr)))
    for theta_i, theta in enumerate(theta_arr):
        P_sin_temp, P1_temp = P1sin(nmax, theta)
        P_sin_orig[:, theta_i] = P_sin_temp
        P1_orig[:, theta_i] = P1_temp

    np.testing.assert_allclose(P1_orig, P1.T)
    np.testing.assert_allclose(P_sin_orig, P_sin.T)


def test_bad_amps():
    beam1 = UVBeam()

    amps = np.ones([2, 8])
    with pytest.raises(ValueError) as cm:
        beam1.read_mwa_beam(filename, pixels_per_deg=1, amplitudes=amps)
    assert str(cm.value).startswith("amplitudes must be shape")


def test_bad_delays():
    beam1 = UVBeam()

    delays = np.zeros([2, 8], dtype="int")
    with pytest.raises(ValueError) as cm:
        beam1.read_mwa_beam(filename, pixels_per_deg=1, delays=delays)
    assert str(cm.value).startswith("delays must be shape")

    delays = np.zeros((2, 16), dtype="int")
    delays = delays + 64
    with pytest.raises(ValueError) as cm:
        beam1.read_mwa_beam(filename, pixels_per_deg=1, delays=delays)
    assert str(cm.value).startswith("There are delays greater than 32")

    delays = np.zeros((2, 16), dtype="float")
    with pytest.raises(ValueError) as cm:
        beam1.read_mwa_beam(filename, pixels_per_deg=1, delays=delays)
    assert str(cm.value).startswith("Delays must be integers.")


def test_dead_dipoles():
    beam1 = UVBeam()

    delays = np.zeros((2, 16), dtype="int")
    delays[:, 0] = 32

    with check_warnings(UserWarning, "There are some terminated dipoles"):
        beam1.read_mwa_beam(filename, pixels_per_deg=1, delays=delays)

    delay_str = (
        "[[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "
        "[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]"
    )
    gain_str = (
        "[[0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "
        "1.0, 1.0, 1.0, 1.0, 1.0], "
        "[0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "
        "1.0, 1.0, 1.0, 1.0]]"
    )
    history_str = (
        "Sujito et al. full embedded element beam, derived from "
        "https://github.com/MWATelescope/mwa_pb/"
        + "  delays set to "
        + delay_str
        + "  gains set to "
        + gain_str
        + beam1.pyuvdata_version_str
    )
    assert utils.history._check_histories(history_str, beam1.history)
