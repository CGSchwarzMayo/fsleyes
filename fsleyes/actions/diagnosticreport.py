#!/usr/bin/env python
#
# diagnosticreport.py - The DiagnosticReportAction
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`DiagnosticReportAction`, which allows
the user to generate a report of the current *FSLeyes* state, to send to me
for bug reporting purposes.
"""


import os
import json
import logging
import platform
from collections import OrderedDict

from   fsl.utils.platform import platform as fslplatform
import fsl.utils.status                   as status
import fsleyes.strings                    as strings
import fsleyes.state                      as fslstate
from . import                                action


log = logging.getLogger(__name__)


class DiagnosticReportAction(action.Action):
    """The ``DiagnosticReportAction`` generates a JSON-formatted report file
    containing information about the current state of *FSLeyes*. When the this
    :class:`.Action` is run, the user is prompted to select a location to save
    the file Then the report is generated, and written out to the specified
    location.
    """

    
    def __init__(self, overlayList, displayCtx, frame):
        """Create a ``DiagnosticReportAction``.

        :arg overlayList: The :class:`.OverlayList`.
        :arg displayCtx:  The master :class:`.DisplayContext`.
        :arg frame:       The :class:`.FSLeyesFrame`.
        """

        action.Action.__init__(self, self.__action)

        self.__frame       = frame
        self.__overlayList = overlayList
        self.__displayCtx  = displayCtx


    def __action(self):
        """This method is the guts of the ``DiagnosticReportAction``. It does
        the following:

          1. Prompts the user to select a location to save the report file.

          2. Generates the report.

          3. Formats the report as JSON.

          4. Saves the report to the specified location.
        """

        import wx

        dlg = wx.FileDialog( 
            self.__frame,
            message=strings.titles[self, 'saveReport'],
            defaultDir=os.getcwd(),
            defaultFile='report.txt',
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)

        if dlg.ShowModal()  != wx.ID_OK:
            return

        path = dlg.GetPath()

        status.update('Writing diagnostic report to {}...'.format(path))

        report = self.__generateReport()
        report = self.__formatReport(report)

        log.debug('Diagnostic report:\n{}'.format(report))

        with open(path, 'wt') as f:
            f.write(report)


    def __generateReport(self):
        """Generates and returns a *report*, a hierarchical dictionary
        containing information about the current system and *FSLeyes*
        state.
        """

        import fsleyes.version as version

        report   = OrderedDict()
        overlays = []
        
        for i, ovl in enumerate(self.__overlayList):
            overlays.append(OrderedDict([
                ('type',   type(ovl).__name__),
                ('name',   ovl.name),
                ('source', ovl.dataSource)]))

        report['Platform']    = platform.platform()
        report['Python']      = '{}  {}'.format(platform.python_version(),
                                                platform.python_compiler())
        report['Version']     = version.__version__
        report['VCS Version'] = version.__vcs_version__
        report['OpenGL']      = self.__openGLReport()
        report['Settings']    = self.__settingsReport()

        state = fslstate.save(self.__frame)

        for k, v in state.items():
            report[k] = v

        return report


    def __settingsReport(self):
        """Creates and returns a dictionary containing:

         - *FSLeyes* settings stored via the :mod:`.settings` module
         - Saved perspectives stored via the :mod:`.perspectives` module.
        """

        import fsleyes.perspectives as perspectives
        import fsl.utils.settings   as fslsettings
        
        report   = OrderedDict()

        # TODO When you update the fsl.utils.settings module,
        #      use its functionality to read out *all* saved
        #      settings, instead of hard coding them here.
        settings = ['fsldir',
                    'fsleyes.frame.layout',
                    'fsleyes.frame.position',
                    'fsleyes.frame.size']
        settings = {s : fslsettings.read(s) for s in settings}

        persps   = perspectives.getAllPerspectives()
        persps   = {p : fslsettings.read('fsleyes.perspectives.{}'.format(p))
                    for p in persps}

        for k, v in settings.items():
            report[k] = str(v)

        report['perspectives'] = ','.join(persps)

        for k, v in persps:
            report['perspectives.{}'.format(k)] = str(v)

        return report


    def __openGLReport(self):
        """Creates and returns a dictionary containing information about the
        OpenGL platform.
        """

        import OpenGL.GL as gl

        report = OrderedDict()

        report['Version']       = gl.glGetString( gl.GL_VERSION)
        report['Compatibility'] = fslplatform.glVersion
        report['Renderer']      = gl.glGetString( gl.GL_RENDERER)
        report['Texture size']  = str(gl.glGetInteger(gl.GL_MAX_TEXTURE_SIZE))
        report['Extensions']    = gl.glGetString( gl.GL_EXTENSIONS).split(' ')

        return report

    
    def __formatReport(self, reportDict):
        """Converts the given hierarchical dictionary to a JSON-formatted
        string.
        """
        return json.dumps(reportDict, indent=2)
