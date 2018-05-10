#!/usr/bin/env python
#
# test_main.py -
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#


import fsleyes.main    as fm
import fsleyes.version as fv


from . import CaptureStdout


def test_version():

    capture  = CaptureStdout()
    exitcode = -1

    try:
        with capture:
            fm.main(['-V'])

    except SystemExit as e:
        exitcode = e.code

    expected = 'fsleyes/FSLeyes version {}'.format(fv.__version__)

    assert exitcode == 0
    assert capture.stdout.strip() == expected
