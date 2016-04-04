#!/usr/bin/env python
#
# selection.py - The Selection class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`Selection` class, which represents a
selection of voxels in a 3D :class:`.Image`.
"""

import logging
import collections

import numpy                       as np
import scipy.ndimage.measurements  as ndimeas

import props


log = logging.getLogger(__name__)


class Selection(props.HasProperties):
    """The ``Selection`` class represents a selection of voxels in a 3D
    :class:`.Image`. The selection is stored as a ``numpy`` mask array,
    the same shape as the image. Methods are available to query and update
    the selection.

    
    Changes to a ``Selection`` can be made through *blocks*, which are 3D
    cuboid regions. The following methods allow a block to be
    selected/deselected, where the block is specified by a voxel coordinate,
    and a block size:

    .. autosummary::
       :nosignatures:

       selectBlock
       deselectBlock


    The following methods offer more fine grained control over selection
    blocks - with these methods, you pass in a block that you have created
    yourself, and an offset into the selection, specifying its location:

    .. autosummary::
       :nosignatures:

       setSelection
       replaceSelection
       addToSelection
       removeFromSelection

    
    A third approach to making a selection is provided by the
    :meth:`selectByValue` method, which allows a selection to be made
    in a manner similar to a *bucket fill* technique found in any image
    editor.

    A ``Selection`` object keeps track of the most recent change made
    through any of the above methods. The most recent change can be retrieved
    through the :meth:`getLastChange` method.


    Finally, the ``Selection`` class offers a few other methods for
    convenience:
    
    .. autosummary::
       :nosignatures:

       getSelectionSize
       clearSelection
       getBoundedSelection
       getIndices
       generateBlock
    """
    

    selection = props.Object()
    """The ``numpy`` mask array containing the current selection is stored
    in a :class:`props.Object`, so that listeners can register to be notified
    whenever it changes.

    .. warning:: Do not modify the selection directly through this attribute -
                 use the ``Selection`` instance methods
                 (e.g. :meth:`setSelection`) instead.  If you modify the
                 selection directly through this attribute, the
                 :meth:`getLastChange` method will break.
    """

    
    def __init__(self, image, display, selection=None):
        """Create a ``Selection`` instance.

        :arg image:     The :class:`.Image` instance  associated with this
                        ``Selection``.
        
        :arg display:   The :class:`.Display` instance for the ``image``.
        
        :arg selection: Selection array. If not provided, one is created.
                        Must be a ``numpy.uint8`` array with the same shape
                        as ``image``. This array is *not* copied.
        """
    
        self.__image              = image
        self.__display            = display
        self.__opts               = display.getDisplayOpts()
        self.__clear              = True
        self.__lastChangeOffset   = None
        self.__lastChangeOldBlock = None
        self.__lastChangeNewBlock = None

        if selection is None:
            selection = np.zeros(image.shape[:3], dtype=np.uint8)
            
        elif selection.shape != image.shape[:3] or \
             selection.dtype != np.uint8:
            raise ValueError('Incompatible selection array: {} ({})'.format(
                selection.shape, selection.dtype))

        self.selection = selection

        log.memory('{}.init ({})'.format(type(self).__name__, id(self)))


    def __del__(self):
        """Prints a log message."""
        if log:
            log.memory('{}.del ({})'.format(type(self).__name__, id(self)))



    def selectBlock(self, voxel, blockSize, axes=(0, 1, 2), combine=False):
        """Selects the block (sets all voxels to 1) specified by the given
        voxel and block size.

        :arg voxel:     Starting voxel coordinates of the block.
        
        :arg blockSize: Size of the block along each axis.
        
        :arg axes:      Limit the block to the specified axes.

        :arg combine:   Combine this change with the previous stored change 
                        (see :meth:`__storeChange`). 
        """
        
        block, offset = self.generateBlock(voxel,
                                           blockSize,
                                           self.selection.shape,
                                           axes)
        
        self.addToSelection(block, offset, combine)

        
    def deselectBlock(self, voxel, blockSize, axes=(0, 1, 2), combine=False):
        """De-selects the block (sets all voxels to 0) specified by the given
        voxel and block size.

        :arg voxel:     Starting voxel coordinates of the block.
        
        :arg blockSize: Size of the block along each axis.
        
        :arg axes:      Limit the block to the specified axes.

        :arg combine:   Combine this change with the previous stored change 
                        (see :meth:`__storeChange`). 
        """

        block, offset = self.generateBlock(voxel,
                                           blockSize,
                                           self.selection.shape,
                                           axes)
        
        self.removeFromSelection(block, offset, combine) 

        
    def setSelection(self, block, offset, combine=False):
        """Copies the given ``block`` into the selection, starting at
        ``offset``.

        :arg block:   A ``numpy.uint8`` array containing a selection.
        
        :arg offset:  Voxel coordinates specifying the block location.

        :arg combine: Combine this change with the previous stored change (see
                      :meth:`__storeChange`). 
        """
        self.__updateSelectionBlock(block, offset, combine) 
        
    
    def replaceSelection(self, block, offset, combine=False):
        """Copies the given ``block`` into the selection, starting at
        ``offset``.
        
        :arg block:   A ``numpy.uint8`` array containing a selection.
        
        :arg offset:  Voxel coordinates specifying the block location.
        
        :arg combine: Combine this change with the previous stored change (see
                      :meth:`__storeChange`). 
        """

        self.__updateSelectionBlock(block, offset, combine)

        
    def addToSelection(self, block, offset, combine=False):
        """Adds the selection (via a boolean OR operation) in the given
        ``block`` to the current selection, starting at ``offset``.

        :arg block:   A ``numpy.uint8`` array containing a selection.
        
        :arg offset:  Voxel coordinates specifying the block location.
                
        :arg combine: Combine this change with the previous stored change (see
                      :meth:`__storeChange`). 
        """
        existing = self.__getSelectionBlock(block.shape, offset)
        block    = np.logical_or(block, existing)
        
        self.__updateSelectionBlock(block, offset, combine)


    def removeFromSelection(self, block, offset, combine=False):
        """Clears all voxels in the selection where the values in ``block``
        are non-zero.
        
        :arg block:   A ``numpy.uint8`` array containing a selection.
        
        :arg offset:  Voxel coordinates specifying the block location.
        
        :arg combine: Combine this change with the previous stored change (see
                      :meth:`__storeChange`).         
        """
        existing             = self.__getSelectionBlock(block.shape, offset)
        existing[block != 0] = False
        self.__updateSelectionBlock(existing, offset, combine)

    
    def getSelectionSize(self):
        """Returns the number of voxels that are currently selected. """
        return self.selection.sum()


    def getBoundedSelection(self):
        """Extracts the smallest region from the :attr:`selection` which
        contains all selected voxels.

        Returns a tuple containing the region, as a ``numpy.uint8`` array, and
        the coordinates specifying its location in the full :attr:`selection`
        array.
        """
        
        xs, ys, zs = np.where(self.selection > 0)

        if len(xs) == 0:
            return np.array([]).reshape(0, 0, 0), (0, 0, 0)

        xlo = xs.min()
        ylo = ys.min()
        zlo = zs.min()
        xhi = xs.max() + 1
        yhi = ys.max() + 1
        zhi = zs.max() + 1

        selection = self.selection[xlo:xhi, ylo:yhi, zlo:zhi]

        return selection, (xlo, ylo, zlo)

        
    def clearSelection(self, restrict=None, combine=False):
        """Clears (sets to 0) the entire selection, or the selection specified
        by the ``restrict`` parameter, if it is given.

        :arg restrict: An optional sequence of three ``slice`` objects,
                       specifying the portion of the selection to clear.

        :arg combine:  Combine this change with the previous stored change (see
                       :meth:`__storeChange`).
        """

        if self.__clear:
            self.__clearChange()
            return

        fRestrict = self.__fixSlices(restrict)
        offset    = [r.start if r.start is not None else 0 for r in fRestrict]

        log.debug('Clearing selection ({}): {}'.format(id(self), fRestrict))

        block                     = np.array(self.selection[fRestrict])
        self.selection[fRestrict] = False

        self.__storeChange(block,
                           np.array(self.selection[fRestrict]),
                           offset,
                           combine)

        # Set the internal clear flag to True,
        # when the entire selection has been
        # cleared, so we can skip subsequent
        # redundant clears.
        if restrict is None:
            self.__clear = True

        self.notify('selection')


    def getLastChange(self):
        """Returns the most recent change made to this ``Selection``.

        A tuple is returned, containing the following:

         - A ``numpy.uint8`` array containing the old block value
         - A ``numpy.uint8`` array containing the new block value
         - Voxel coordinates denoting the block location in the full
           :attr:`selection` array.
        """

        return (self.__lastChangeOldBlock,
                self.__lastChangeNewBlock,
                self.__lastChangeOffset)


    def __clearChange(self):
        """
        """
        self.__lastChangeOldBlock = None
        self.__lastChangeNewBlock = None
        self.__lastChangeOffset   = None


    def __storeChange(self, old, new, offset, combine=False):
        """Stores the given selection change.

        :arg old:     A copy of the portion of the :attr:`selection` that 
                      has changed,
        
        :arg new:     The new selection values.
        
        :arg offset:  Offset into the full :attr:`selection` array
        
        :arg combine: If ``False`` (the default), the previously stored change
                      will be replaced by the current change. Otherwise the
                      previous and current changes will be combined.
        """

        # Not combining changes (or there
        # is no previously stored change).
        # We store the change, replacing
        # the previous one.
        if (not combine) or (self.__lastChangeOldBlock is None):

            if log.getEffectiveLevel() == logging.DEBUG:
                log.debug('Replacing previously stored change with: '
                          '[({}, {}), ({}, {}), ({}, {})] ({} selected)'
                          .format(offset[0], offset[0] + old.shape[0],
                                  offset[1], offset[1] + old.shape[1],
                                  offset[2], offset[2] + old.shape[2],
                                  new.sum()))
            
            self.__lastChangeOldBlock = old
            self.__lastChangeNewBlock = new
            self.__lastChangeOffset   = offset
            return

        # Otherwise, we combine the old
        # change with the new one.
        lcOld     = self.__lastChangeOldBlock
        lcNew     = self.__lastChangeNewBlock
        lcOffset  = self.__lastChangeOffset

        # Calculate/organise low/high indices
        # for each change set:
        # 
        #  - one for the current change (passed
        #    in to this method call)
        #
        #  - One for the last stored change
        #
        #  - One for the combination of the above
        currIdxs = []
        lastIdxs = []
        cmbIdxs  = []

        for ax in range(3):

            currLo = offset[  ax]
            lastLo = lcOffset[ax]
            currHi = offset[  ax] + old  .shape[ax]
            lastHi = lcOffset[ax] + lcOld.shape[ax]

            cmbLo  = min(currLo, lastLo)
            cmbHi  = max(currHi, lastHi)

            currIdxs.append((currLo, currHi))
            lastIdxs.append((lastLo, lastHi))
            cmbIdxs .append((cmbLo,  cmbHi))

        # Make slice objects for each of the indices,
        # to make indexing easier. The last/current
        # slice objects are defined relative to the
        # combined space of both.
        cmbSlices  = [slice(lo, hi) for lo, hi in cmbIdxs]
        
        lastSlices = [slice(lLo - cmLo, lHi - cmLo)
                      for ((lLo, lHi), (cmLo, cmHi))
                      in zip(lastIdxs, cmbIdxs)]
        
        currSlices = [slice(cuLo - cmLo, cuHi - cmLo)
                      for ((cuLo, cuHi), (cmLo, cmHi))
                      in zip(currIdxs, cmbIdxs)]

        cmbOld    = np.array(self.selection[cmbSlices])
        cmbNew    = np.array(cmbOld)

        cmbOld[lastSlices] = lcOld
        cmbNew[lastSlices] = lcNew
        cmbNew[currSlices] = new

        if log.getEffectiveLevel() == logging.DEBUG:
            log.debug('Combining changes: '
                      '[({}, {}), ({}, {}), ({}, {})] ({} selected) + '
                      '[({}, {}), ({}, {}), ({}, {})] ({} selected) = '
                      '[({}, {}), ({}, {}), ({}, {})] ({} selected)'.format(
                          lastIdxs[0][0], lastIdxs[0][1],
                          lastIdxs[1][0], lastIdxs[1][1],
                          lastIdxs[2][0], lastIdxs[2][1],
                          lcNew.sum(),
                          currIdxs[0][0], currIdxs[0][1],
                          currIdxs[1][0], currIdxs[1][1],
                          currIdxs[2][0], currIdxs[2][1],
                          new.sum(),
                          cmbIdxs[0][0], cmbIdxs[0][1],
                          cmbIdxs[1][0], cmbIdxs[1][1],
                          cmbIdxs[2][0], cmbIdxs[2][1],
                          cmbNew.sum()))
        
        self.__lastChangeOldBlock = cmbOld
        self.__lastChangeNewBlock = cmbNew
        self.__lastChangeOffset   = cmbIdxs[0][0], cmbIdxs[1][0], cmbIdxs[2][0]


    def getIndices(self, restrict=None):
        """Returns a :math:`N \\times 3` array which contains the
        coordinates of all voxels that are currently selected.

        If the ``restrict`` argument is not provided, the entire
        selection image is searched.

        :arg restrict: A ``slice`` object specifying a sub-set of the
                       full selection to consider.
        """

        restrict   = self.__fixSlices(restrict)
        xs, ys, zs = np.where(self.selection[restrict])
        result     = np.vstack((xs, ys, zs)).T

        for ax in range(3):
            
            off = restrict[ax].start
            
            if off is not None:
                result[:, ax] += off

        return result


    def selectByValue(self,
                      seedLoc,
                      precision=None,
                      searchRadius=None,
                      local=False,
                      restrict=None,
                      combine=False):
        """A *bucket fill* style selection routine. Given a seed location,
        finds all voxels which have a value similar to that of that location.
        The current selection is replaced with all voxels that were found.

        :arg seedLoc:      Voxel coordinates specifying the seed location

        :arg precision:    Voxels which have a value that is less than
                           ``precision`` from the seed location value will
                           be selected.

        :arg searchRadius: May be either a single value, or a sequence of
                           three values - one for each axis. If provided, the
                           search is limited to a sphere (in the voxel
                           coordinate system), centred on the seed location,
                           with the specified ``searchRadius`` (in voxels). If
                           not provided, the search will cover the entire
                           image space.

        :arg local:        If ``True``, a voxel will only be selected if it
                           is adjacent to an already selected voxel (using
                           8-neighbour connectivity).

        :arg restrict:     An optional sequence of three ``slice`` object,
                           specifying a sub-set of the image to search.

        :arg combine:      Combine with the previous stored change (see
                           :meth:`__storeChange`).
        """

        if   len(self.__image.shape) == 3:
            data = self.__image.data
        elif len(self.__image.shape) == 4:
            data = self.__image.data[:, :, :, self.__opts.volume]
        else:
            raise RuntimeError('Only 3D and 4D images are currently supported')

        shape   = data.shape
        seedLoc = np.array(seedLoc)
        value   = data[seedLoc[0], seedLoc[1], seedLoc[2]]

        # Search radius may be either None, a scalar value,
        # or a sequence of three values (one for each axis).
        # If it is one of the first two options (None/scalar),
        # turn it into the third.
        if searchRadius is None:
            searchRadius = np.array([0, 0, 0])
        elif not isinstance(searchRadius, collections.Sequence):
            searchRadius = np.array([searchRadius] * 3)
            
        searchRadius = np.ceil(searchRadius)
        searchOffset = (0, 0, 0)

        # Reduce the data set if
        # restrictions have been
        # specified
        if restrict is not None:

            restrict = self.__fixSlices(restrict)
            xs, xe   = restrict[0].start, restrict[0].step
            ys, ye   = restrict[1].start, restrict[1].step
            zs, ze   = restrict[2].start, restrict[2].step

            if xs is None: xs = 0
            if ys is None: ys = 0
            if zs is None: zs = 0
            if xe is None: xe = data.shape[0]
            if ye is None: ye = data.shape[1]
            if ze is None: ze = data.shape[2]

            # The seed location has to be in the sub-set
            # o the image specified by the restrictions
            if seedLoc[0] < xs or seedLoc[0] >= xe or \
               seedLoc[1] < ys or seedLoc[1] >= ye or \
               seedLoc[2] < zs or seedLoc[2] >= ze:
                raise ValueError('Seed location ({}) is outside '
                                 'of restrictions ({})'.format(
                                     seedLoc, ((xs, xe), (ys, ye), (zs, ze))))
                
            data         = data[restrict]
            shape        = data.shape
            searchOffset = [start for start in [xs, ys, zs]]
            seedLoc      = [sl - so for sl, so in zip(seedLoc, searchOffset)]

        # No search radius - search
        # through the entire image
        if np.any(searchRadius == 0):
            searchSpace  = data
            searchMask   = None

        # Search radius specified - limit
        # the search space, and specify
        # an ellipsoid mask with the
        # specified per-axis radii
        else:            
            ranges = [None, None, None]
            slices = [None, None, None]

            # Calculate xyz indices 
            # of the search space
            for ax in range(3):

                idx = seedLoc[     ax]
                rad = searchRadius[ax]

                lo = idx - rad
                hi = idx + rad + 1

                if lo < 0:             lo = 0
                if hi > shape[ax] - 1: hi = shape[ax]

                ranges[ax] = np.arange(lo, hi)
                slices[ax] = slice(    lo, hi)

            xs, ys, zs = np.meshgrid(*ranges, indexing='ij')

            # Centre those indices and the
            # seed location at (0, 0, 0)
            xs         -= seedLoc[0]
            ys         -= seedLoc[1]
            zs         -= seedLoc[2]
            seedLoc[0] -= ranges[0][0]
            seedLoc[1] -= ranges[1][0]
            seedLoc[2] -= ranges[2][0]

            # Distances from each point in the search
            # space to the centre of the search space
            dists = ((xs / searchRadius[0]) ** 2 +
                     (ys / searchRadius[1]) ** 2 +
                     (zs / searchRadius[2]) ** 2)

            # Extract the search space, and
            # create the ellipsoid mask
            searchSpace  = data[slices]
            searchOffset = [so + r[0] for so, r in zip(searchOffset, ranges)]
            searchMask   = dists <= 1

        if precision is None: hits = searchSpace == value
        else:                 hits = np.abs(searchSpace - value) < precision

        if searchMask is not None:
            hits[~searchMask] = False

        # If local is true, limit the selection to
        # adjacent points with the same/similar value
        # (using scipy.ndimage.measurements.label)
        #
        # If local is not True, any same or similar 
        # values are part of the selection
        if local:
            hits, _   = ndimeas.label(hits)
            seedLabel = hits[seedLoc[0], seedLoc[1], seedLoc[2]]
            hits      = hits == seedLabel

        self.replaceSelection(hits, searchOffset, combine)

    
    def transferSelection(self, destImg, destDisplay):
        """Re-samples the current selection into the destination image
        space. 

        Each ``Selection`` instance is in terms of a specific :class:`.Image`
        instance, which has a specific dimensionality. In order to apply
        a ``Selection`` which is in terms of one ``Image``, the selection
        array needs to be re-sampled.
        
        :arg destImg:     The :class:`.Image` that the selection is to be
                          transferred to.

        :arg destDisplay: The :class:`.Display` instance associated with
                          ``destImg``.

        :returns: a new ``numpy.uint8`` array, suitable for creating a new
                 ``Selection`` object for use with the given ``destImg``.
        """
        raise NotImplementedError('todo')
        

    def __updateSelectionBlock(self, block, offset, combine=False):
        """Replaces the current selection at the specified ``offset`` with the
        given ``block``.

        The old values for the block are stored, and can be retrieved via the
        :meth:`getLastChange` method.

        :arg block:   A ``numpy.uint8`` array containing the new selection
                      values.

        :arg offset:  Voxel coordinates specifying the location of ``block``.

        :arg combine: Combine with the previous stored change (see
                      :meth:`__storeChange`).
        """

        block = np.array(block, dtype=np.uint8)

        if block.size == 0:
            return

        if offset is None:
            offset = (0, 0, 0)

        xlo, ylo, zlo = offset
        xhi           = xlo + block.shape[0]
        yhi           = ylo + block.shape[1]
        zhi           = zlo + block.shape[2]

        self.__storeChange(
            np.array(self.selection[xlo:xhi, ylo:yhi, zlo:zhi]),
            np.array(block),
            offset,
            combine)

        log.debug('Updating selection ({}) block [{}:{}, {}:{}, {}:{}]'.format(
            id(self), xlo, xhi, ylo, yhi, zlo, zhi))

        self.selection[xlo:xhi, ylo:yhi, zlo:zhi] = block

        self.__clear = False
        
        self.notify('selection') 

        
    def __getSelectionBlock(self, size, offset):
        """Extracts a block from the selection image starting from the
        specified ``offset``, and of the specified ``size``.
        """
        
        xlo, ylo, zlo = offset
        xhi, yhi, zhi = size

        xhi = xlo + size[0]
        yhi = ylo + size[1]
        zhi = zlo + size[2]

        return np.array(self.selection[xlo:xhi, ylo:yhi, zlo:zhi])


    def __fixSlices(self, slices):
        """A convenience method used by :meth:`selectByValue`,
        :meth:`clearSelection` and :meth:`getIndices`, to sanitise their
        ``restrict`` parameter.
        """

        if slices is None:
            slices = [None, None, None]

        if len(slices) != 3:
            raise ValueError('Three slice objects are required')

        for i, s in enumerate(slices):
            if s is None:
                slices[i] = slice(None)

        return slices
        
    
    @classmethod
    def generateBlock(cls, voxel, blockSize, shape, axes=(0, 1, 2)):
        """Convenience method to generates a square/cube of ones, with the
        specified voxel at its centre, to fit in an image of the given shape.

        If the specified voxel would result in part of the block being located
        outside of the image shape, the block is truncated to fit inside
        the image bounds.

        :arg voxel:     Coordinates of the voxel around which the block is to
                        be centred.
        
        :arg blockSize: Desired width/height/depth
        
        :arg shape:     Shape of the image in which the block is to be located.
        
        :arg axes:      Axes along which the block is to be located.

        :returns:       A tuple containing the block - a ``numpy.uint8`` array
                        filled with ones, and an offset specifying the block
                        location within an image of the specified ``shape``.
        """

        if blockSize == 1:
            return np.array([True], dtype=np.uint8).reshape(1, 1, 1), voxel

        blockLo = [v - int(np.floor((blockSize - 1) / 2.0)) for v in voxel]
        blockHi = [v + int(np.ceil(( blockSize - 1) / 2.0)) for v in voxel]

        for i in range(3):
            if i not in axes:
                blockLo[i] = voxel[i]
                blockHi[i] = voxel[i] + 1
            else:
                blockLo[i] = max(blockLo[i],     0)
                blockHi[i] = min(blockHi[i] + 1, shape[i])

            if blockHi[i] <= blockLo[i]:
                return np.ones((0, 0, 0), dtype=np.uint8), voxel

        block = np.ones((blockHi[0] - blockLo[0],
                         blockHi[1] - blockLo[1],
                         blockHi[2] - blockLo[2]), dtype=np.uint8)

        offset = blockLo

        return block, offset