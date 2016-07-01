#!/usr/bin/env python
#
# gltensor.py - The GLTensor class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`GLTensor` class, for displaying tensor
ellipsoids in a :class:`.TensorImage` overlay.

See :mod:`.gl21.gltensor_funcs`.
"""


import numpy                as np

import OpenGL.GL            as gl

import fsl.utils.async      as async

import fsleyes.gl           as fslgl
import fsleyes.gl.resources as glresources
import fsleyes.gl.textures  as textures
from . import                  glvector


class GLTensor(glvector.GLVector):
    """The ``GLTensor`` class encapsulates the logic required to render
    :class:`.TensorImage` overlays.  Most of the functionality is in the
    :mod:`.gl21.gltensor_funcs` module.

    
    .. note:: The ``GLTensor`` is not currently supported on versions of
              OpenGL older than 2.1 (and probably never will be).


    The eigenvalues and eigenvectors of the ``TensorImage`` are stored as 3D
    :class:`.ImageTexture` instances, using the :mod:`.gl.resources`
    module. These textures are added as attributes of a GLTensor instance -
    this is in addition to the textures that are used for :class:`.GLVector`
    instances (of which the ``GLTensor`` is a sub-class):

      ============== ================== ==================
      Attribute name Description        Texture unit
      ============== ================== ==================
      ``v1Texture``  First eigenvector  ``gl.GL_TEXTURE8``
      ``v2Texture``  Second eigenvector ``gl.GL_TEXTURE9``
      ``v3Texture``  Third eigenvector  ``gl.GL_TEXTURE10``
      ``l1Texture``  First eigenvalue   ``gl.GL_TEXTURE11``
      ``l2Texture``  Second eigenvalue  ``gl.GL_TEXTURE12``
      ``l3Texture``  Third eigenvalue   ``gl.GL_TEXTURE13``
      ============== ================== ==================
    """

    
    def __init__(self, image, display, xax, yax):
        """Create a ``GLTensor``. Prepares the eigenvalue and eigenvector
        textures, and calls the :func:`.gl21.gltensor_funcs.init` function.

        :arg image:   A :class:`.TensorImage` overlay.
        
        :arg display: The :class:`.Display` instance associated with the
                      ``image``.
        
        :arg xax:     Initial display X axis

        :arg yax:     Initial display Y axis
        """

        prefilter = np.abs
        def prefilterRange(dmin, dmax):
            return max((0, dmin)), max((abs(dmin), abs(dmax)))

        # This function will get called via
        # GLVector.__init__ when all of its
        # textures are ready.
        def onInit():

            v1 = image.V1()
            v2 = image.V2()
            v3 = image.V3()
            l1 = image.L1()
            l2 = image.L2()
            l3 = image.L3()

            def vPrefilter(d):
                return d.transpose((3, 0, 1, 2))

            # Create a texture for each eigenvalue/
            # vector, and add each of them as suitably
            # named attributes on this GLTensor
            # instance.
            names      = ['v1', 'v2', 'v3', 'l1', 'l2', 'l3']
            imgs       = [ v1,   v2,   v3,   l1,   l2,   l3]
            texThreads = []

            for  name, img in zip(names, imgs):
                texName = '{}_{}_{}'.format(type(self).__name__, name, id(img))

                if name[0] == 'v':
                    prefilter = vPrefilter
                    nvals     = 3
                else:
                    prefilter = None
                    nvals     = 1

                tex = glresources.get(
                    texName,
                    textures.ImageTexture,
                    texName,
                    img,
                    nvals=nvals,
                    normalise=True,
                    prefilter=prefilter)

                texThreads.append(tex.refreshThread())

                setattr(self, '{}Texture'.format(name), tex)

            # gltensor_funcs.init must only be called
            # after all textures are ready, so we
            # set up a wait thread on all of the texture
            # refresh threads.
            #
            # When the textures created in GLVector.__init__
            # are ready, this function (onInit) will be called.
            # The return value of this function is a wait
            # thread which will finish when the V123/L123
            # textures are ready. GLVector.__init__ will then
            # set up a wait thread on this wait thread, to
            # do the final initialisation. It's all a little
            # ugly.
            return async.wait(texThreads,
                              lambda: fslgl.gltensor_funcs.init(self))
        
        glvector.GLVector.__init__(self,
                                   image,
                                   display,
                                   xax,
                                   yax,
                                   prefilter=prefilter,
                                   prefilterRange=prefilterRange,
                                   vectorImage=image.V1(),
                                   init=onInit)


    def destroy(self):
        """Must be called when this ``GLTensor`` is no longer needed. Performs
        cleanup tasks.
        """
        glvector.GLVector.destroy(self)
        fslgl.gltensor_funcs.destroy(self)
        
        names = ['v1', 'v2', 'v3', 'l1', 'l2', 'l3']

        for name in names:
            attrName = '{}Texture'.format(name)
            tex      = getattr(self, attrName)

            glresources.delete(tex.getTextureName())
            setattr(self, attrName, None)


    def ready(self):
        """Returns ``True`` if this ``GLTensor`` is ready to be drawn,
        ``False`` otherwise.
        """

        return (glvector.GLVector.ready(self) and
                self.v1Texture is not None    and 
                self.v2Texture is not None    and 
                self.v3Texture is not None    and 
                self.l1Texture is not None    and 
                self.l2Texture is not None    and 
                self.l3Texture is not None    and
                self.v1Texture.ready()        and
                self.v2Texture.ready()        and
                self.v3Texture.ready()        and
                self.l1Texture.ready()        and
                self.l2Texture.ready()        and
                self.l3Texture.ready())


    def addListeners(self):
        """Overrides :meth:`.GLVector.addListeners`. Calls the base class
        implementation, and adds some property listeners to the
        :class:`.TensorOpts` instance associated with the 
        :class:`.TensorImage` being displayed.
        """
        glvector.GLVector.addListeners(self)

        name = self.name
        opts = self.displayOpts

        def shaderUpdate(*a):
            if self.ready():
                self.updateShaderState()
                self.notify()

        opts.addListener('lighting',         name, shaderUpdate, weak=False)
        opts.addListener('neuroFlip',        name, shaderUpdate, weak=False)
        opts.addListener('tensorResolution', name, shaderUpdate, weak=False)
        opts.addListener('tensorScale',      name, shaderUpdate, weak=False)
        

    def removeListeners(self):
        """Overrides :meth:`.GLVector.removeListeners`. Calls the base class
        implementation, and removes some property listeners.
        """
        glvector.GLVector.removeListeners(self)

        name = self.name
        opts = self.displayOpts
        
        opts.removeListener('lighting',         name)
        opts.removeListener('neuroFlip',        name)
        opts.removeListener('tensorResolution', name)
        opts.removeListener('tensorScale',      name)

        
    def getDataResolution(self, xax, yax):
        """Overrides :meth:`.GLVector.getDataResolution`. Returns a pixel
        resolution suitable for off-screen rendering of this ``GLTensor``.
        """

        res       = list(glvector.GLVector.getDataResolution(self, xax, yax))
        res[xax] *= 20
        res[yax] *= 20
        
        return res


    def compileShaders(self):
        """Overrides :meth:`.GLVector.compileShaders`. Calls the
        :func:`.gl21.gltensor_funcs.compileShaders` function.
        """
        fslgl.gltensor_funcs.compileShaders(self)


    def updateShaderState(self):
        """Overrides :meth:`.GLVector.updateShaderState`. Calls the
        :func:`.gl21.gltensor_funcs.updateShaderState` function.
        """ 
        return fslgl.gltensor_funcs.updateShaderState(self)

        
    def preDraw(self):
        """Overrides :meth:`.GLVector.preDraw`. Binds the eigenvalue and
        eigenvector textures, calls the :meth:`.GLVector.preDraw` method,
        and the :func:`.gl21.gltensor_funcs.preDraw` function.
        """

        self.v1Texture.bindTexture(gl.GL_TEXTURE8)
        self.v2Texture.bindTexture(gl.GL_TEXTURE9)
        self.v3Texture.bindTexture(gl.GL_TEXTURE10)
        self.l1Texture.bindTexture(gl.GL_TEXTURE11)
        self.l2Texture.bindTexture(gl.GL_TEXTURE12)
        self.l3Texture.bindTexture(gl.GL_TEXTURE13)
        
        glvector.GLVector.preDraw(self)
        fslgl.gltensor_funcs.preDraw(self)


    def draw(self, zpos, xform=None):
        """Overrides :meth:`.GLVector.draw`. Calls the
        :func:`.gl21.gltensor_funcs.draw` function.
        """
        fslgl.gltensor_funcs.draw(self, zpos, xform)


    def postDraw(self):
        """Overrides :meth:`.GLVector.postDraw`. Unbinds the eigenvalue and
        eigenvector textures, calls the :meth:`.GLVector.postDraw` method, and
        the :func:`.gl21.gltensor_funcs.postDraw` function.
        """
    
        self.v1Texture.unbindTexture()
        self.v2Texture.unbindTexture()
        self.v3Texture.unbindTexture()
        self.l1Texture.unbindTexture()
        self.l2Texture.unbindTexture()
        self.l3Texture.unbindTexture()
        
        glvector.GLVector.postDraw(self)
        fslgl.gltensor_funcs.postDraw(self)
