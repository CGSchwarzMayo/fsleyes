#!/usr/bin/env python
#
# __init__.py - Functions for OpenGL 1.4 rendering.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This package contains modules for rendering various :class:`.GLObject`
types in an OpenGL 1.4 compatible manner. The following modules currently
exist:

.. autosummary::

   ~fsleyes.gl.gl14.glvolume_funcs
   ~fsleyes.gl.gl14.glrgbvector_funcs
   ~fsleyes.gl.gl14.gllinevector_funcs
   ~fsleyes.gl.gl14.glmodel_funcs
   ~fsleyes.gl.gl14.gllabel_funcs
"""

from . import glvolume_funcs
from . import glrgbvector_funcs
from . import gllinevector_funcs
from . import glmodel_funcs
from . import gllabel_funcs

gltensor_funcs = None