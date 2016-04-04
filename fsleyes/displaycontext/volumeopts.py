#!/usr/bin/env python
#
# volumeopts.py - Defines the VolumeOpts class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module defines the :class:`Nifti1Opts` and :class:`VolumeOpts` classes.


.. _volumeopts-coordinate-systems:


---------------------------------------
An important note on coordinate systems
---------------------------------------


*FSLeyes* displays all overlays in a single coordinate system, referred
throughout as the *display coordinate system*. However, :class:`.Nifti1`
overlays can potentially be displayed in one of three coordinate systems:


 ====================== ====================================================
 **voxel** space        (a.k.a. ``id``) The image data voxel coordinates
                        map to the display coordinates.

 **scaled voxel** space (a.k.a. ``pixdim``) The image data voxel coordinates
                        are scaled by the ``pixdim`` values stored in the
                        NIFTI1 header.

 **world** space        (a.k.a. ``affine``) The image data voxel coordinates
                        are transformed by the ``qform``/``sform``
                        transformation matrix stored in the NIFTI1 header.
 ====================== ====================================================


The :attr:`Nifti1Opts.transform` property controls how the image data is
transformed into the display coordinate system. It allows any of the above
spaces to be specified (as ``id``, ``pixdim`` or ``affine``` respectively),
and also allows a ``custom`` transformation to be specified (see the
:attr:`customXform` property).


Regardless of the space in which the ``Nifti1`` is displayed , the
voxel-to-display space transformation assumes that integer voxel coordinates
correspond to the centre of the voxel in the display coordinate system. In
other words, a voxel at location::

    [x, y, z]


will be transformed such that, in the display coordinate system, it occupies
the space::

    [x-0.5 - x+0.5, y-0.5 - y+0.5, z-0.5 - z+0.5]


For example, if the :attr:`Nifti1Opts.transform` property is set to ``id``, the
voxel::

    [2, 3, 4]

is drawn such that it occupies the space::

    [1.5 - 2.5, 2.5 - 3.5, 3.5 - 4.5]


This convention is in line with the convention defined by the ``NIFTI1``
specification: it assumes that the voxel coordinates ``[x, y, z]`` correspond
to the centre of a voxel.
"""


import logging

import numpy        as np
import numpy.linalg as npla

import props

import fsl.data.image      as fslimage
import fsl.utils.transform as transform
import fsleyes.colourmaps  as fslcm
import fsleyes.actions     as actions
from . import display      as fsldisplay


log = logging.getLogger(__name__)


class Nifti1Opts(fsldisplay.DisplayOpts):
    """The ``Nifti1Opts`` class describes how a :class:`.Nifti1` overlay
    should be displayed.

    
    ``Nifti1Opts`` is the base class for a number of :class:`.DisplayOpts`
    sub-classes - it contains display options which are common to all overlay
    types that represent a NIFTI1 image.
    """

    
    volume = props.Int(minval=0, maxval=0, default=0, clamped=True)
    """If the ``Image`` is 4D, the current volume to display.""" 

    
    resolution = props.Real(maxval=10, default=1, clamped=True)
    """Data resolution in the image world coordinate system. The minimum
    value is configured in :meth:`__init__`.
    """ 


    transform = props.Choice(
        ('affine', 'pixdim', 'id', 'custom'),
        default='pixdim')
    """This property defines how the overlay should be transformd into
    the display coordinate system. See the
    :ref:`note on coordinate systems <volumeopts-coordinate-systems>`
    for important information regarding this property.
    """

    
    customXform = props.Array(
        dtype=np.float64,
        shape=(4, 4),
        resizable=False,
        default=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    """A custom transformation matrix which is used when the :attr:`transform`
    property is set to ``custom``.
    """

 
    def __init__(self, *args, **kwargs):
        """Create a ``Nifti1Opts`` instance.

        All arguments are passed through to the :class:`.DisplayOpts`
        constructor.
        """

        # The transform property cannot be unsynced
        # across different displays, as it affects
        # the display context bounds, which also
        # cannot be unsynced
        nounbind = kwargs.get('nounbind', [])
        nounbind.append('transform')
        nounbind.append('customXform')

        kwargs['nounbind'] = nounbind

        fsldisplay.DisplayOpts.__init__(self, *args, **kwargs)

        overlay = self.overlay

        self.addListener('transform',
                         self.name,
                         self.__transformChanged,
                         immediate=True)
        self.addListener('customXform',
                         self.name,
                         self.__customXformChanged,
                         immediate=True)

        # The display<->* transformation matrices
        # are created in the _setupTransforms method
        self.__xforms = {}
        self.__setupTransforms()
        self.__transformChanged()
 
        # is this a 4D volume?
        if self.overlay.is4DImage():
            self.setConstraint('volume', 'maxval', overlay.shape[3] - 1)

        # limit resolution to the image dimensions
        self.resolution = min(overlay.pixdim[:3])
        self.setConstraint('resolution', 'minval', self.resolution)


    def destroy(self):
        """Calls the :meth:`.DisplayOpts.destroy` method. """
        self.removeListener('transform',   self.name)
        self.removeListener('customXform', self.name)
        fsldisplay.DisplayOpts.destroy(self)

        
    def __transformChanged(self, *a):
        """Called when the :attr:`transform` property changes.
        
        Calculates the min/max values of a 3D bounding box, in the display
        coordinate system, which is big enough to contain the image. Sets the
        :attr:`.DisplayOpts.bounds` property accordingly.
        """

        oldValue = self.getLastValue('transform')

        if oldValue is None:
            oldValue = self.transform

        self.displayCtx.cacheStandardCoordinates(
            self.overlay,
            self.transformCoords(self.displayCtx.location.xyz,
                                 oldValue,
                                 'world'))

        lo, hi = transform.axisBounds(
            self.overlay.shape[:3],
            self.getTransform('voxel', 'display'))
        
        self.bounds[:] = [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]


    def __customXformChanged(self, *a):
        """Called when the :attr:`customXform` property changes.  Re-generates
        transformation matrices, and re-calculates the display :attr:`bounds`
        (via calls to :meth:`__setupTransforms` and
        :meth:`__transformChanged`).
        """

        stdLoc = self.displayToStandardCoordinates(
            self.displayCtx.location.xyz)
        
        self.__setupTransforms()
        if self.transform == 'custom':
            self.__transformChanged()

            # if transform == custom, the cached value
            # calculated in __transformChanged will be
            # wrong, so we have to overwrite it here.
            # The stdLoc value calculated above is valid,
            # because it was calculated before the
            # transformation matrices were recalculated
            # in __setupTransforms
            self.displayCtx.cacheStandardCoordinates(self.overlay, stdLoc)
 
        
    def __setupTransforms(self):
        """Calculates transformation matrices between all of the possible
        spaces in which the overlay may be displayed.

        These matrices are accessible via the :meth:`getTransform` method.
        """

        image = self.overlay

        voxToIdMat         = np.eye(4)
        voxToPixdimMat     = np.diag(list(image.pixdim[:3]) + [1.0])
        voxToPixFlipMat    = np.array(voxToPixdimMat)
        voxToAffineMat     = image.voxToWorldMat.T
        voxToCustomMat     = self.customXform

        # pixdim-flip space differs from
        # pixdim space only if the affine
        # matrix has a positive determinant
        if npla.det(voxToAffineMat) > 0:
            x               = image.shape[0]
            flip            = transform.scaleOffsetXform([-1, 1, 1], [x, 0, 0])
            voxToPixFlipMat = transform.concat(voxToPixFlipMat, flip)

        idToVoxMat         = transform.invert(voxToIdMat)
        idToPixdimMat      = transform.concat(idToVoxMat, voxToPixdimMat)
        idToPixFlipMat     = transform.concat(idToVoxMat, voxToPixFlipMat)
        idToAffineMat      = transform.concat(idToVoxMat, voxToAffineMat)
        idToCustomMat      = transform.concat(idToVoxMat, voxToCustomMat)

        pixdimToVoxMat     = transform.invert(voxToPixdimMat)
        pixdimToIdMat      = transform.concat(pixdimToVoxMat, voxToIdMat)
        pixdimToPixFlipMat = transform.concat(pixdimToVoxMat, voxToPixFlipMat)
        pixdimToAffineMat  = transform.concat(pixdimToVoxMat, voxToAffineMat)
        pixdimToCustomMat  = transform.concat(pixdimToVoxMat, voxToCustomMat)

        pixFlipToVoxMat    = transform.invert(voxToPixFlipMat)
        pixFlipToIdMat     = transform.concat(pixFlipToVoxMat, voxToIdMat)
        pixFlipToPixdimMat = transform.concat(pixFlipToVoxMat, voxToPixdimMat)
        pixFlipToAffineMat = transform.concat(pixFlipToVoxMat, voxToAffineMat)
        pixFlipToCustomMat = transform.concat(pixFlipToVoxMat, voxToCustomMat)

        affineToVoxMat     = image.worldToVoxMat.T
        affineToIdMat      = transform.concat(affineToVoxMat, voxToIdMat)
        affineToPixdimMat  = transform.concat(affineToVoxMat, voxToPixdimMat)
        affineToPixFlipMat = transform.concat(affineToVoxMat, voxToPixFlipMat)
        affineToCustomMat  = transform.concat(affineToVoxMat, voxToCustomMat)

        customToVoxMat     = transform.invert(voxToCustomMat)
        customToIdMat      = transform.concat(customToVoxMat, voxToIdMat)
        customToPixdimMat  = transform.concat(customToVoxMat, voxToPixdimMat)
        customToPixFlipMat = transform.concat(customToVoxMat, voxToPixFlipMat)
        customToAffineMat  = transform.concat(customToVoxMat, voxToAffineMat)

        self.__xforms['id',  'id']          = np.eye(4)
        self.__xforms['id',  'pixdim']      = idToPixdimMat
        self.__xforms['id',  'pixdim-flip'] = idToPixFlipMat 
        self.__xforms['id',  'affine']      = idToAffineMat
        self.__xforms['id',  'custom']      = idToCustomMat

        self.__xforms['pixdim', 'pixdim']      = np.eye(4)
        self.__xforms['pixdim', 'id']          = pixdimToIdMat
        self.__xforms['pixdim', 'pixdim-flip'] = pixdimToPixFlipMat
        self.__xforms['pixdim', 'affine']      = pixdimToAffineMat
        self.__xforms['pixdim', 'custom']      = pixdimToCustomMat

        self.__xforms['pixdim-flip', 'pixdim-flip'] = np.eye(4)
        self.__xforms['pixdim-flip', 'id']          = pixFlipToIdMat
        self.__xforms['pixdim-flip', 'pixdim']      = pixFlipToPixdimMat
        self.__xforms['pixdim-flip', 'affine']      = pixFlipToAffineMat
        self.__xforms['pixdim-flip', 'custom']      = pixFlipToCustomMat 
 
        self.__xforms['affine', 'affine']      = np.eye(4)
        self.__xforms['affine', 'id']          = affineToIdMat
        self.__xforms['affine', 'pixdim']      = affineToPixdimMat
        self.__xforms['affine', 'pixdim-flip'] = affineToPixFlipMat
        self.__xforms['affine', 'custom']      = affineToCustomMat

        self.__xforms['custom', 'custom']      = np.eye(4)
        self.__xforms['custom', 'id']          = customToIdMat
        self.__xforms['custom', 'pixdim']      = customToPixdimMat
        self.__xforms['custom', 'pixdim-flip'] = customToPixFlipMat
        self.__xforms['custom', 'affine']      = customToAffineMat


    def getTransform(self, from_, to, xform=None):
        """Return a matrix which may be used to transform coordinates
        from ``from_`` to ``to``. Valid values for ``from_`` and ``to``
        are:

        
        =============== ======================================================
        ``id``          Voxel coordinates
        
        ``voxel``       Equivalent to ``id``.
        
        ``pixdim``      Voxel coordinates, scaled by voxel dimensions

        ``pixdim-flip`` Voxel coordinates, scaled by voxel dimensions, and
                        with the X axis flipped if the affine matrix has
                        a positivie determinant. If the affine matrix does
                        not have a positive determinant, this is equivalent to
                        ``pixdim``.

        ``pixflip``     Equivalent to ``pixdim-flip``.
        
        ``affine``      World coordinates, as defined by the NIFTI1
                        ``qform``/``sform``. See :attr:`.Image.voxToWorldMat`.

        ``world``       Equivalent to ``affine``.

        ``custom``      Coordinates in the space defined by the custom
                        transformation matrix, as specified via the
                        :attr:`customXform` property.
        
        ``display``     Equivalent to the current value of :attr:`transform`.
        =============== ======================================================

        
        If the ``xform`` parameter is provided, and one of ``from_`` or ``to``
        is ``display``, the value of ``xform`` is used instead of the current
        value of :attr:`transform`.

        
        .. note:: While the ``pixdim-flip`` space is not a display option for
                  ``Nifti1``, the transformations for this space are made
                  available theough this method as it is the coordinate system
                  used internally by many of the FSL tools.  Most importantly,
                  this is the coordinate system used in the VTK sub-cortical
                  segmentation model files output by FIRST, and is hence used
                  by the :class:`.ModelOpts` class to transform VTK model
                  coordinates.

                  http://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FLIRT/FAQ#What_is_the_\
                  format_of_the_matrix_used_by_FLIRT.2C_and_how_does_it_\
                  relate_to_the_transformation_parameters.3F
        """

        if xform is None:
            xform = self.transform

        if   from_ == 'display': from_ = xform
        elif from_ == 'world':   from_ = 'affine'
        elif from_ == 'voxel':   from_ = 'id'
        elif from_ == 'pixflip': from_ = 'pixdim-flip'
        
        if   to    == 'display': to    = xform
        elif to    == 'world':   to    = 'affine'
        elif to    == 'voxel':   to    = 'id'
        elif to    == 'pixflip': to    = 'pixdim-flip'

        return self.__xforms[from_, to]


    def getTransformOffsets(self, from_, to_):
        """Returns a set of offsets which should be applied to coordinates
        before/after applying a transfromation.  
        
        When an image is displayed in ``id``, ``pixdim`` and ``affine`` space,
        voxel coordinates map to the voxel centre, so our voxel from above will
        occupy the space ``(-0.5 - 0.5, 0.5 - 1.5, 1.5 - 2.5)``. This is
        dictated by the NIFTI specification. See the
        :ref:`note on coordinate systems <volumeopts-coordinate-systems>`.

        
        This function returns some offsets to ensure that the coordinate
        transformation from the source space to the target space is valid,
        given the above requirements.


        A tuple containing two sets of offsets (each of which is a tuple of
        three values). The first set is to be applied to the source
        coordinates (in the ``from_`` space) before transformation, and the
        second set to the target coordinates (in the ``to_`` space) after the
        transformation.

        
        See also the :meth:`transformCoords` method, which will perform the
        transformation correctly for you, without you having to worry about
        these silly offsets.

        
        .. note:: This method was written during a crazy time when, in ``id``
                  or ``pixdim`` space, voxels ``(0, 0, 0)`` of images overlaid
                  on each other were aligned at the voxel corner, whereas in
                  ``affine`` space, they were aligned at the voxel
                  centre. This is no longer the case, so this method is not
                  actually necessary, and just returns all zeros. But it is
                  still here, and still being used, just in case we need to
                  change these conventions again in the future.
        """
        return (0, 0, 0), (0, 0, 0)


    def transformCoords(self, coords, from_, to_, vround=False):
        """Transforms the given coordinates from ``from_`` to ``to_``.

        The ``from_`` and ``to_`` parameters must both be one of:
        
           - ``display``: The display coordinate system
           - ``voxel``:   The image voxel coordinate system
           - ``world``:   The image world coordinate system
           - ``custom``:  The coordinate system defined by the custom
                          transformation matrix (see :attr:`customXform`)

        :arg coords: Coordinates to transform
        :arg from_:  Space to transform from
        :arg to_:    Space to transform to
        :arg vround: If ``True``, and ``to_ == 'voxel'``, the transformed
                     coordinates are rounded to the nearest integer.
        """

        xform     = self.getTransform(       from_, to_)
        pre, post = self.getTransformOffsets(from_, to_)
        
        coords    = np.array(coords)                   + pre
        coords    = transform.transform(coords, xform) + post
        
        # Round to integer voxel coordinates?
        if to_ == 'voxel' and vround:

            # The transformation matrices treat integer
            # voxel coordinates as the voxel centre (e.g.
            # a voxel [3, 4, 5] fills the space:
            # 
            # [2.5-3.5, 3.5-4.5, 4.5-5.5].
            #
            # So all we need to do is round to the
            # nearest integer.
            #
            # Note that the numpy.round function breaks
            # ties (e.g. 7.5) by rounding to the nearest
            # *even* integer, which can cause funky
            # behaviour. So we take (floor(x)+0.5) instead
            # of rounding, to force consistent behaviour
            # (i.e. always rounding central values up).
            coords = np.floor(coords + 0.5)

        return coords

    
    def getVoxel(self, xyz=None, clip=True, vround=True):
        """Calculates and returns the voxel coordinates corresponding to the
        given location (assumed to be in the display coordinate system) for
        the :class:`.Nifti1` associated with this ``Nifti1Opts`` instance..

        :arg xyz:    Display space location to convert to voxels. If not
                     provided, the current :attr:`.DisplayContext.location`
                     is used.

        :arg clip:   If ``False``, and the transformed coordinates are out of
                     the voxel coordinate bounds, the coordinates returned
                     anyway. Defaults to ``True``.


        :arg vround: If ``True``, the returned voxel coordinates are rounded
                     to the nearest integer. Otherwise they may be fractional.
                    

        :returns:    ``None`` if the location is outside of the image bounds,
                     unless ``clip=False``.
        """

        if xyz is not None: x, y, z = xyz
        else:               x, y, z = self.displayCtx.location.xyz

        overlay = self.overlay
        vox     = self.transformCoords([[x, y, z]],
                                       'display',
                                       'voxel',
                                       vround=vround)[0]

        if vround:
            vox = [int(v) for v in vox]

        if not clip:
            return vox

        for ax in (0, 1, 2):
            if vox[ax] < 0 or vox[ax] >= overlay.shape[ax]:
                return None

        return vox


    def displayToStandardCoordinates(self, coords):
        """Overrides :meth:`.DisplayOpts.displayToStandardCoordinates`.
        Transforms the given display system coordinates into the world
        coordinates of the :class:`.Nifti1` associated with this
        ``Nifti1Opts`` instance.
        """
        return self.transformCoords(coords, 'display', 'world')

    
    def standardToDisplayCoordinates(self, coords):
        """Overrides :meth:`.DisplayOpts.standardToDisplayCoordinates`.
        Transforms the given coordinates (assumed to be in the world
        coordinate system of the ``Nifti1`` associated with this ``Nifti1Opts``
        instance) into the display coordinate system.
        """ 
        return self.transformCoords(coords, 'world', 'display')


class VolumeOpts(Nifti1Opts):
    """The ``VolumeOpts`` class defines options for displaying :class:`.Image`
    instances as regular 3D volumes.

    The ``VolumeOpts`` class links the :attr:`.Display.brightness` and
    :attr:`.Display.contrast` properties to its own :attr:`displayRange`
    property, so changes in either of the former will result in a change to
    the latter, and vice versa. This relationship is defined by the
    :func:`~.colourmaps.displayRangeToBricon` and
    :func:`~.colourmaps.briconToDisplayRange` functions, in the
    :mod:`.colourmaps` module.

    In addition to all of the display properties, ``VolumeOpts`` instances
    have the following attributes:

    =========== ===============================
    ``dataMin`` The minimum value in the image.
    ``dataMax`` The maximum value in the image.
    =========== ===============================

    For large images (where *large* is arbitrarily defined in
    :meth:`__init__`), the ``dataMin`` and ``dataMax`` attributes will contain
    range of a sample of the image data, rather their actual values. This is
    purely to eliminate the need to calculate minimum/maximum values over very
    large (and potentially memory-mapped) images, which can be a time
    consuming operation.


    ``VolumeOpts`` instances provide the following  :mod:`.actions`:

    .. autosummary::
       :nosignatures:

       resetDisplayRange
    """

    
    displayRange = props.Bounds(ndims=1, clamped=False)
    """Image values which map to the minimum and maximum colour map colours.
    The values that this property can take are unbound because of the
    interaction between it and the :attr:`.Display.brightness` and
    :attr:`.Display.contrast` properties.
    """

    
    clippingRange = props.Bounds(ndims=1)
    """Values outside of this range are not shown.  Clipping works as follows:
    
     - Image values less than or equal to the minimum clipping value are
       clipped.

     - Image values greater than or equal to the maximum clipping value are
       clipped. 
    """

    
    invertClipping = props.Boolean(default=False)
    """If ``True``, the behaviour of :attr:`clippingRange` is inverted, i.e.
    values inside the clipping range are clipped, instead of those outside
    the clipping range.
    """

    
    clipImage = props.Choice()
    """Clip voxels according to the values in another image. By default, voxels
    are clipped by the values in the image itself - this property allows the
    user to choose another image by which voxels are to be clipped. Any image
    which is in the :class:`.OverlayList`, and which has the same voxel
    dimensions as the primary image can be selected for clipping. The
    :attr:`clippingRange` property dictates the values outside of which voxels
    are clipped.
    """ 

    
    cmap = props.ColourMap()
    """The colour map, a :class:`matplotlib.colors.Colourmap` instance."""


    negativeCmap = props.ColourMap()
    """A second colour map, used if :attr:`useNegativeCmap` is ``True``.
    When active, the :attr:`cmap` is used to colour positive values, and
    the :attr:`negativeCmap` is used to colour negative values.
    """

    
    useNegativeCmap = props.Boolean(default=False)
    """When ``True``, the :attr:`cmap` is used to colour positive values,
    and the :attr:`negativeCmap` is used to colour negative values.
    When this property is enabled, the minimum value for both the
    :attr:`displayRange` and :attr:`clippingRange` is set to zero. Both
    ranges are applied to positive values, and negated/inverted for negative
    values.

    .. note:: When this property is set to ``True``, the
              :attr:`.Display.brightness` and :attr:`.Display.contrast`
              properties are disabled, as managing the interaction between
              them would be far too complicated.
    """

    
    interpolation = props.Choice(('none', 'linear', 'spline'))
    """How the value shown at a real world location is derived from the
    corresponding data value(s). ``none`` is equivalent to nearest neighbour
    interpolation.
    """


    invert = props.Boolean(default=False)
    """Use an inverted version of the current colour map (see the :attr:`cmap`
    property).
    """


    linkLowRanges = props.Boolean(default=True)
    """If ``True``, the low bounds on both the :attr:`displayRange` and
    :attr:`clippingRange` ranges will be linked together.
    """

    
    linkHighRanges = props.Boolean(default=False)
    """If ``True``, the high bounds on both the :attr:`displayRange` and
    :attr:`clippingRange` ranges will be linked together.
    """ 


    def __init__(self,
                 overlay,
                 display,
                 overlayList,
                 displayCtx,
                 **kwargs):
        """Create a :class:`VolumeOpts` instance for the specified ``overlay``,
        assumed to be an :class:`.Image` instance.

        All arguments are passed through to the :class:`.DisplayOpts`
        constructor.
        """

        # The dataRangeChanged method needs acces to the
        # overlay, but we want to update the display/
        # clipping range before calling the constructor,
        # as we would otherwise clobber values inherited
        # from the parent VolumeOpts (if any).
        self.overlay = overlay

        self.__dataRangeChanged()
        self.displayRange.x = [self.dataMin, self.dataMax]
        
        Nifti1Opts.__init__(self,
                            overlay,
                            display,
                            overlayList,
                            displayCtx,
                            **kwargs)
        
        # The displayRange property of every child VolumeOpts
        # instance is linked to the corresponding 
        # Display.brightness/contrast properties, so changes
        # in one are reflected in the other. This interaction
        # complicates the relationship between parent and child
        # VolumeOpts instances, so we only implement it on
        # children.
        #
        # NOTE: This means that if we use a parent-less
        #       DisplayContext for display, this bricon-display
        #       range relationship will break.
        #
        self.__registered = self.getParent() is not None
        if self.__registered:

            overlay    .addListener('dataRange',
                                    self.name,
                                    self.__dataRangeChanged)
            display    .addListener('brightness',
                                    self.name,
                                    self.__briconChanged)
            display    .addListener('contrast',
                                    self.name,
                                    self.__briconChanged)
            self       .addListener('displayRange',
                                    self.name,
                                    self.__displayRangeChanged)

            # In fact, the interaction between many of the
            # VolumeOpts properties really screws with
            # the parent-child sync relationship, so I'm
            # just completely avoiding it by only registering
            # listeners on child instances. See note above
            # about why this will probably break future
            # usage.
            overlayList.addListener('overlays',
                                    self.name,
                                    self.__overlayListChanged)
 
            self       .addListener('useNegativeCmap',
                                    self.name,
                                    self.__useNegativeCmapChanged)
            self       .addListener('linkLowRanges',
                                    self.name,
                                    self.__linkLowRangesChanged)
            self       .addListener('linkHighRanges',
                                    self.name,
                                    self.__linkHighRangesChanged)
            self       .addListener('clipImage',
                                    self.name,
                                    self.__clipImageChanged)

            # Because displayRange and bri/con are intrinsically
            # linked, it makes no sense to let the user sync/unsync
            # them independently. So here we are binding the boolean
            # sync properties which control whether the dRange/bricon
            # properties are synced with their parent. So when one
            # property is synced/unsynced, the other ones are too.
            self.bindProps(self   .getSyncPropertyName('displayRange'),
                           display,
                           display.getSyncPropertyName('brightness'))
            self.bindProps(self   .getSyncPropertyName('displayRange'), 
                           display,
                           display.getSyncPropertyName('contrast'))

            # If useNegativeCmap, linkLowRanges or linkHighRanges
            # have been set to True (this will happen if they
            # are true on the parent VolumeOpts instance), make
            # sure the property / listener states are up to date.
            if self.useNegativeCmap: self.__useNegativeCmapChanged()
            if self.linkLowRanges:   self.__linkLowRangesChanged()
            if self.linkHighRanges:  self.__linkHighRangesChanged()

            if not self.isSyncedToParent('clipImage'):
                self.__overlayListChanged()
            if not self.isSyncedToParent('clippingRange'):
                self.__clipImageChanged()

        # If we have a parent, the clipImage and
        # clippingRange settings will have been
        # synced to the parent instance. Otherwise,
        # we need to configure their initial values.
        else:
            self.__overlayListChanged()
            self.__clipImageChanged()


    def destroy(self):
        """Removes property listeners, and calls the :meth:`Nifti1Opts.destroy`
        method.
        """

        if self.__registered:

            overlayList = self.overlayList
            display     = self.display
            overlayList.removeListener('overlays',        self.name) 
            display    .removeListener('brightness',      self.name)
            display    .removeListener('contrast',        self.name)
            self       .removeListener('displayRange',    self.name)
            self       .removeListener('useNegativeCmap', self.name)
            self       .removeListener('linkLowRanges',   self.name)
            self       .removeListener('linkHighRanges',  self.name)
            self       .removeListener('clipImage',       self.name)
            
            self.unbindProps(self   .getSyncPropertyName('displayRange'),
                             display,
                             display.getSyncPropertyName('brightness'))
            self.unbindProps(self   .getSyncPropertyName('displayRange'), 
                             display,
                             display.getSyncPropertyName('contrast'))
            
            self.__linkRangesChanged(False, 0)
            self.__linkRangesChanged(False, 1)

        Nifti1Opts.destroy(self)


    @actions.action
    def resetDisplayRange(self):
        """Resets the display range to the data range."""
        self.displayRange.x = [self.dataMin, self.dataMax]


    def __updateDataRange(self, absolute=False):
        """Configures the minimum/maximum bounds of the :attr:`displayRange`
        and :attr:`clippingRange` properties.
        """

        dataMin = self.overlay.dataRange.xlo
        dataMax = self.overlay.dataRange.xhi

        dmin = dataMin
        dmax = dataMax
        
        if absolute:
            dmin = min((0,            abs(dataMin)))
            dmax = max((abs(dataMin), abs(dataMax)))

        self.dataMin           = dataMin
        self.dataMax           = dataMax
        self.displayRange.xmin = dmin
        self.displayRange.xmax = dmax

        # If a clipping image is set, 
        # we use its range instead of 
        # our overlay's range, for the
        # clippingRange property.
        if self.clipImage is not None:
            dmin = self.clipImage.dataRange.xlo
            dmax = self.clipImage.dataRange.xhi

        # Clipping works on >= and <=, so we add
        # a small offset to the clipping limits
        # so the user can configure the scene such
        # that no values are clipped.
        distance = abs(dmax - dmin) / 100.0

        self.clippingRange.xmin = dmin - distance
        self.clippingRange.xmax = dmax + distance


    def __dataRangeChanged(self, *a):
        """Called when the :attr:`.Image.dataRange` property changes.
        Updates the limits of the :attr:`displayRange` and
        :attr:`.clippingRange` properties.
        """
        self.__updateDataRange(absolute=self.useNegativeCmap)
 

    def __overlayListChanged(self, *a):
        """Called when the :`class:`.OverlayList` changes. Updates the
        options of the :attr:`clipImage` property.
        """
        
        clipProp = self.getProp('clipImage')
        clipVal  = self.clipImage
        overlays = self.displayCtx.getOrderedOverlays()
        
        options  = [None]

        for overlay in overlays:
            
            if overlay is self.overlay:                     continue
            if not isinstance(overlay, fslimage.Image):     continue
            if overlay.shape[:3] != self.overlay.shape[:3]: continue

            options.append(overlay)

        clipProp.setChoices(options, instance=self)

        if clipVal in options: self.clipImage = clipVal
        else:                  self.clipImage = None 
    
        
    def __clipImageChanged(self, *a):
        """Called when the :attr:`clipImage` property is changed. Updates
         the range of the :attr:`clippingRange` property.
        """

        if self.clipImage is None:
            dataMin = self.dataMin
            dataMax = self.dataMax
            
            self.enableProperty('linkLowRanges')
            self.enableProperty('linkHighRanges') 
        else:
            dataMin = self.clipImage.dataRange.xlo
            dataMax = self.clipImage.dataRange.xhi

            # If the clipping range is based on another
            # image, it makes no sense to link the low/
            # high display/clipping ranges, as they are
            # probably different. So if a clip image is
            # selected, we disable the link range
            # properties.
            if self.propertyIsEnabled('linkLowRanges'):

                self.disableListener('linkLowRanges',  self.name)
                self.disableListener('linkHighRanges', self.name)
 
                self.linkLowRanges  = False
                self.linkHighRanges = False
            
                self.__linkLowRangesChanged()
                self.__linkHighRangesChanged()

                self.disableProperty('linkLowRanges')
                self.disableProperty('linkHighRanges')
                self.enableListener('linkLowRanges',  self.name)
                self.enableListener('linkHighRanges', self.name) 
            
        log.debug('Clip image changed for {}: {} - new '
                  'clipping range: [{: 0.5f} - {: 0.5f}]'.format(
                      self.overlay,
                      self.clipImage,
                      dataMin,
                      dataMax))

        self.__updateDataRange(absolute=self.useNegativeCmap)

        self.clippingRange.x = dataMin, self.clippingRange.xmax


    def __toggleListeners(self, enable=True):
        """This method enables/disables the property listeners which
        are registered on the :attr:`displayRange` and
        :attr:`.Display.brightness`/:attr:`.Display.contrast`/properties.
        
        Because these properties are linked via the
        :meth:`__displayRangeChanged` and :meth:`__briconChanged` methods,
        we need to be careful about avoiding recursive callbacks.

        Furthermore, because the properties of both :class:`VolumeOpts` and
        :class:`.Display` instances are possibly synchronised to a parent
        instance (which in turn is synchronised to other children), we need to
        make sure that the property listeners on these other sibling instances
        are not called when our own property values change. So this method
        disables/enables the property listeners on all sibling ``VolumeOpts``
        and ``Display`` instances.
        """

        parent = self.getParent()

        # this is the parent instance
        if parent is None:
            return

        # The parent.getChildren() method will
        # contain this VolumeOpts instance,
        # so the below loop toggles listeners
        # for this instance and all of the other
        # children of the parent
        peers  = parent.getChildren()

        for peer in peers:

            if not any((peer.display.isSyncedToParent('brightness'),
                        peer.display.isSyncedToParent('contrast'),
                        peer.        isSyncedToParent('displayRange'))):
                continue

            bri = peer.display.hasListener('brightness',   peer.name)
            con = peer.display.hasListener('contrast',     peer.name)
            dr  = peer        .hasListener('displayRange', peer.name)

            if enable:
                if bri: peer.display.enableListener('brightness',   peer.name)
                if con: peer.display.enableListener('contrast',     peer.name)
                if dr:  peer        .enableListener('displayRange', peer.name)
            else:
                if bri: peer.display.disableListener('brightness',   peer.name)
                if con: peer.display.disableListener('contrast',     peer.name)
                if dr:  peer        .disableListener('displayRange', peer.name)
                

    def __briconChanged(self, *a):
        """Called when the ``brightness``/``contrast`` properties of the
        :class:`.Display` instance change.
        
        Updates the :attr:`displayRange` property accordingly.

        See :func:`.colourmaps.briconToDisplayRange`.
        """

        dlo, dhi = fslcm.briconToDisplayRange(
            (self.dataMin, self.dataMax),
            self.display.brightness / 100.0,
            self.display.contrast   / 100.0)

        self.__toggleListeners(False)
        self.displayRange.x = [dlo, dhi]
        self.__toggleListeners(True)

        
    def __displayRangeChanged(self, *a):
        """Called when the `attr:`displayRange` property changes.

        Updates the :attr:`.Display.brightness` and :attr:`.Display.contrast`
        properties accordingly.

        See :func:`.colourmaps.displayRangeToBricon`.
        """

        if self.useNegativeCmap:
            return

        brightness, contrast = fslcm.displayRangeToBricon(
            (self.dataMin, self.dataMax),
            self.displayRange.x)
        
        self.__toggleListeners(False)

        # update bricon
        self.display.brightness = brightness * 100
        self.display.contrast   = contrast   * 100

        self.__toggleListeners(True)


    def __useNegativeCmapChanged(self, *a):
        """Called when the :attr:`useNegativeCmap` property changes.
        Enables/disables the :attr:`.Display.brightness` and
        :attr:`.Display.contrast` properties, and configures limits
        on the :attr:`clippingRange` and :attr:`displayRange` properties.
        """

        if self.useNegativeCmap:
            self.display.disableProperty('brightness')
            self.display.disableProperty('contrast')
        else:
            self.display.enableProperty('brightness')
            self.display.enableProperty('contrast')

        self.__updateDataRange(absolute=self.useNegativeCmap)
            


    def __linkLowRangesChanged(self, *a):
        """Called when the :attr:`linkLowRanges` property changes. Calls the
        :meth:`__linkRangesChanged` method.
        """
        self.__linkRangesChanged(self.linkLowRanges, 0)

        
    def __linkHighRangesChanged(self, *a):
        """Called when the :attr:`linkHighRanges` property changes. Calls the
        :meth:`__linkRangesChanged` method.
        """ 
        self.__linkRangesChanged(self.linkHighRanges, 1) 

        
    def __linkRangesChanged(self, val, idx):
        """Called when either the :attr:`linkLowRanges` or
        :attr:`linkHighRanges` properties change. Binds/unbinds the specified
        range properties together.

        :arg val: Boolean indicating whether the range values should be
                  linked or unlinked.
        
        :arg idx: Range value index - 0 corresponds to the low range value,
                  and 1 to the high range value.
        """

        dRangePV = self.displayRange .getPropertyValueList()[idx]
        cRangePV = self.clippingRange.getPropertyValueList()[idx]

        if props.propValsAreBound(dRangePV, cRangePV) == val:
            return

        props.bindPropVals(dRangePV,
                           cRangePV,
                           bindval=True,
                           bindatt=False,
                           unbind=not val)

        if val:
            cRangePV.set(dRangePV.get())