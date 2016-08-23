#!/usr/bin/env python
#
# runscript.py - The RunScriptAction class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`RunScriptAction` class, which allows
the user to run a custom Python script.

The following functions are used by the :class:`RunScriptAction`, and are
available for other purposes:

 .. autosummary::
    :nosignatures:

    runScript
    fsleyesScriptEnvironment
"""


from __future__ import print_function

import __future__          as futures
import                        os
import os.path             as op
import                        logging
import                        collections

import fsl.utils.settings  as fslsettings
import fsleyes.strings     as strings
from . import                 action


log = logging.getLogger(__name__)


class RunScriptAction(action.Action):
    """The ``RunScriptAction`` class is an :class:`.Actuion` which allows the
    user to run a custom Python script to control *FSLeyes*. The user is
    prompted to select a script, and then the script is compiled and exceuted.
    """


    def __init__(self, overlayList, displayCtx, frame):
        """Create a ``RunScriptAction``.

        :arg overlayList: The :class:`.OverlayList`.
        :arg displayCtx:  The top-level :class:`.DisplayContext`.
        :arg overlayList: The :class:`.FSLEyesFrame`.
        """
        action.Action.__init__(self, self.__doAction)

        self.__frame       = frame
        self.__overlayList = overlayList
        self.__displayCtx  = displayCtx
        

    def __doAction(self, script=None):
        """Called when this :class:`.Action` is invoked. If the ``script``
        argument is ``None``, the user is prompted  to select a script file.
        The script is then compiled and executed.
        """

        import wx

        if script is None:

            lastDir = fslsettings.read('runScriptLastDir')

            if lastDir is None:
                lastDir = os.getcwd()

            msg = strings.messages[self, 'runScript']

            # Ask the user what script
            # they want to run
            dlg    = wx.FileDialog(self.__frame,
                                   message=msg,
                                   defaultDir=lastDir,
                                   wildcard='*.py',
                                   style=wx.FD_OPEN)

            if dlg.ShowModal() != wx.ID_OK:
                return

            script = dlg.GetPath()

            # Save the script directory for the
            # next time the user is prompted 
            fslsettings.write('runScriptLastDir', op.dirname(script))

        # Run the script, show an
        # error if it crashes
        try:
            runScript(self.__frame,
                      self.__overlayList,
                      self.__displayCtx,
                      script)
            
        except Exception as e:
            log.warning('Script ({}) could not be executed: {}'.format(
                        script,
                        str(e)),
                        exc_info=True)

            msg = strings.messages[self, 'crash'].format(
                script,
                str(e))

            wx.MessageDialog(self.__frame,
                             message=msg,
                             style=wx.OK | wx.ICON_ERROR).ShowModal()
            
            return

        
def runScript(frame, overlayList, displayCtx, script):
    """Compiles and executes the given file, assumed to be a Python script.
    An ``Error`` is raised if the script cannot be compiled or executed.
    """

    # We want scripts to be Python3-like
    flags = (futures.print_function  .compiler_flag |
             futures.absolute_import .compiler_flag |
             futures.division        .compiler_flag | 
             futures.unicode_literals.compiler_flag)

    # Is the script a file?
    if op.exists(script):
        with open(script, 'rt') as f:
            log.debug('Loading script {}...'.format(script))
            code = f.read()

    # If not, assume it's
    # a code snippet
    else:
        code = script

    # Compile the script
    log.debug('Compiling {}...'.format(script))
    code = compile(code,
                   script,
                   mode='exec',
                   flags=flags,
                   dont_inherit=True)

    _globals, _locals = fsleyesScriptEnvironment(frame,
                                                 overlayList,
                                                 displayCtx)

    # Run the script
    log.debug('Running {}...'.format(script))
    eval(code, _globals, _locals)


def fsleyesScriptEnvironment(frame, overlayList, displayCtx):
    """Creates and returns two dictionaries, to be used as the ``globals``
    and ``locals`` dictionaries when executing a custom FSLeyes python
    script.
    """
    
    # Set up the script environment. It's
    # quite difficult to truly sand-box an
    # eval'ed piece of code, but restricting
    # the things contained in__builtins__
    # will deter simple attack attempts.
    _globals = {
        '__builtins__' : {
            'True'  : True,
            'False' : False
        },
    }
    
    import fsleyes.views         as views
    import fsleyes.controls      as controls
    import fsl.data.image        as image
    import fsl.data.featimage    as featimage
    import fsl.data.melodicimage as melimage
    import fsl.data.tensorimage  as tensorimage
    import fsl.data.model        as model


    def load(filename):
        """Load the specified file into FSLeyes. """
        
        from . import                 loadoverlay
        import fsleyes.autodisplay as autodisplay

        def onLoad(overlays):

            if len(overlays) == 0:
                return
            
            overlayList.append(overlays[0])

            if displayCtx.autoDisplay:
                autodisplay.autoDisplay(overlays[0],
                                        overlayList,
                                        displayCtx) 
        
        loadoverlay.loadOverlays([filename],
                                 onLoad=onLoad,
                                 inmem=displayCtx.loadInMemory)
        

    def trueScaledVoxels():
        """Display all NIFTI images in true scaled voxels (without
        any radiological/neurological flip). """
        for o in overlayList:
            if isinstance(o, image.Nifti):
                displayCtx.getOpts(o).transform = 'pixdim'
                
    def rawVoxels():
        """Display all NIFTI images in raw voxels. """
        for o in overlayList:
            if isinstance(o, image.Nifti):
                displayCtx.getOpts(o).transform = 'id'
                
    _locals = collections.OrderedDict((
        ('Image',            image.Image),
        ('FEATImage',        featimage.FEATImage),
        ('MelodicImage',     melimage.MelodicImage),
        ('TensorImage',      tensorimage.TensorImage),
        ('Model',            model.Model),
        ('views',            views),
        ('controls',         controls),
        ('overlayList',      overlayList),
        ('displayCtx',       displayCtx),
        ('frame',            frame),
        ('trueScaledVoxels', trueScaledVoxels),
        ('rawVoxels',        rawVoxels),
        ('load',             load),
        ('print',            print),
    ))

    return _globals, _locals
