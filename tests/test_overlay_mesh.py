#!/usr/bin/env python
#
# test_overlay_mesh.py -
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#

import pytest
import fsl.data.image as fslimage

from . import run_cli_tests, fliporient


pytestmark = pytest.mark.clitest


cli_tests = """
mesh_l_thal.vtk -mc 1 0 0
mesh_l_thal.vtk -mc 1 0 0 -o
mesh_l_thal.vtk -mc 1 0 0    -w 1
mesh_l_thal.vtk -mc 1 0 0    -w 5
mesh_l_thal.vtk -mc 1 0 0    -w 10
mesh_l_thal.vtk -mc 1 0 0 -o -w 1
mesh_l_thal.vtk -mc 1 0 0 -o -w 5
mesh_l_thal.vtk -mc 1 0 0 -o -w 10

# We're really making sure here that images/meshes are
# displayed correctly, regardless of whether the reference
# image is in neurological or radiological orientation.

{{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}}                 # Should display correctly
{{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s id           # Should display incorrectly
{{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s pixdim       # Should display incorrectly
{{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s pixdim-flip  # Should display correctly
{{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s affine       # Should display incorrectly

-ds world {{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}}                 # Should display correctly
-ds world {{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s id           # Should display incorrectly
-ds world {{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s pixdim       # Should display incorrectly
-ds world {{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s pixdim-flip  # Should display correctly
-ds world {{fliporient('mesh_ref.nii.gz')}} mesh_l_thal.vtk -mc 0.5 0.5 1 -r {{fliporient('mesh_ref.nii.gz')}} -s affine       # Should display incorrectly

mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz                 # Should display correctly
mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s id           # Should display correctly (because t1 is 1mm isotropic)
mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s pixdim       # Should display correctly
mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s pixdim-flip  # Should display correctly
mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s affine       # Should display incorrectly

-ds world mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz                 # Should display correctly
-ds world mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s id           # Should display correctly (because t1 is 1mm isotropic)
-ds world mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s pixdim       # Should display correctly
-ds world mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s pixdim-flip  # Should display correctly
-ds world mesh_ref.nii.gz mesh_l_thal.vtk -mc 0.5 0.5 1 -r mesh_ref.nii.gz -s affine       # Should display incorrectly

# Vertex data
mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data3d.txt -cm hot
mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data4d.txt -cm hot -vdi 3
mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data3d.txt -cm hot -cr 25 100
mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data3d.txt -cm hot -cr 25 100 -dc

mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data3d.txt -l random -ul
mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data3d.txt -l random -ul -cr 25 100
mesh_l_thal.vtk -mc 1 0 0 -o -w 10 -vd mesh_l_thal_data3d.txt -l random -ul -cr 25 100 -dc
"""


def test_overlay_mesh():
    extras = {
        'fliporient' : fliporient,
    }
    run_cli_tests('test_overlay_mesh', cli_tests, extras=extras)
