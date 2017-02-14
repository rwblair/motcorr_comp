#!/usr/bin/env python
# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
Created on Wed Dec  2 17:35:40 2015

@author: craigmoodie
"""
import os
from copy import deepcopy
from time import strftime

from nipype.algorithms.confounds import ComputeDVARS, FramewiseDisplacement
from nipype.pipeline import engine as pe
from nipype.interfaces import c3, fsl, utility
from nipype.interfaces import utility as niu
from nipype.interfaces.ants.preprocess import AntsMotionCorr, AntsMotionCorrStats, AntsMatrixConversion
from niworkflows.interfaces.masks import ComputeEPIMask

from fmriprep.interfaces import BIDSDataGrabber, DerivativesDataSink
from fmriprep.utils.misc import collect_bids_data, get_biggest_epi_file_size_gb
from fmriprep.workflows.confounds import _gather_confounds
from fmriprep.workflows import confounds

def base_workflow_enumerator(subject_list, task_id, settings):
    workflow = pe.Workflow(name='workflow_enumerator')
    generated_list = []
    for subject in subject_list:
        generated_workflow = base_workflow_generator(subject, task_id=task_id,
                                                     settings=settings)
        if generated_workflow:
            cur_time = strftime('%Y%m%d-%H%M%S')
            generated_workflow.config['execution']['crashdump_dir'] = (
                os.path.join(settings['output_dir'], 'log', subject, cur_time)
            )
            for node in generated_workflow._get_all_nodes():
                node.config = deepcopy(generated_workflow.config)
            generated_list.append(generated_workflow)
    workflow.add_nodes(generated_list)

    return workflow


def base_workflow_generator(subject_id, task_id, settings):
    subject_data = collect_bids_data(settings['bids_root'], subject_id, task_id)

    settings["biggest_epi_file_size_gb"] = get_biggest_epi_file_size_gb(subject_data['func'])

    if subject_data['t1w'] == []:
        raise Exception(
            "No T1w images found for participant %s. All workflows require T1w images."%subject_id
        )

    return mottcorr_comp(subject_data, settings, name=subject_id)

def mottcorr_comp(subject_data, settings, name='mottcorr_comp'):

    if settings is None:
        settings = {}

    workflow = pe.Workflow(name=name)
    outputnode = pe.Node(niu.IdentityInterface(
        fields=['silly_out', 'silly_out2']), name='outputnode')
    bidssrc = pe.Node(BIDSDataGrabber(subject_data=subject_data), name='BIDSDatasource')

    ants_hmc = test_ants(settings=settings)
    ants_hmc.get_node('inputnode').iterables = ('epi', subject_data['func'])

    fsl_hmc = test_fsl(settings=settings)
    fsl_hmc.get_node('inputnode').iterables = ('epi', subject_data['func'])

    workflow.add_nodes([ants_hmc, fsl_hmc])

    return workflow

def test_ants(name='test_antsmottcorr', settings=None):
    workflow = pe.Workflow(name=name)
    inputnode = pe.Node(niu.IdentityInterface(fields=['epi']), name='inputnode')
    outputnode = pe.Node(niu.IdentityInterface(
        fields=['epi_hmc', 'dvars_out', 'epi_mask']), name='outputnode')


    ants_mean = pe.Node(AntsMotionCorr(), name='ANTS_mean')
    ants_hmc_config = {
        'metric_type': 'GC',
        'metric_weight': 1,
        'radius_or_bins': 1,
        'sampling_strategy': "Random",
        'sampling_percentage': 0.05,
        'iterations': 10,
        'smoothing_sigmas': 0,
        'shrink_factors': 1,
        'n_images': 10,
        'use_fixed_reference_image': True,
        'use_scales_estimator': True,
        'output_warped_image': 'warped.nii.gz',
        'output_transform_prefix': 'motcorr',
        'transformation_model': 'Affine',
        'gradient_step_length': 0.005
    }

    ants_hmc = pe.Node(AntsMotionCorr(**ants_hmc_config),
                       name='EPI_ANTS_hmc')
    skullstrip_epi = pe.Node(ComputeEPIMask(generate_report=True, dilation=1),
                             name='ComputeEPIMask')

    dvars = pe.Node(ComputeDVARS(save_all=True, remove_zerovariance=True),
                    name='ants_DVARS')
    dvars.interface.estimated_memory_gb = settings[
                                              "biggest_epi_file_size_gb"] * 3

    frame_displace = pe.Node(FramewiseDisplacement(),
                             name="FramewiseDisplacement")
    frame_displace.interface.estimated_memory_gb = settings[
                                              "biggest_epi_file_size_gb"] * 3

    ants_fd = pe.Node(
        AntsMotionCorrStats(output="frame_displacement.csv", framewise=False),
        name='ants_fd'
    )

    params = pe.Node(AntsMatrixConversion(), name='ants_params')

    concat = pe.Node(
        utility.Function(
            function=_gather_confounds,
            input_names=['dvars', 'frame_displace'],
            output_names=['combined_out']
        ),
        name="ConcatConfounds"
    )

    workflow.connect([
        (inputnode, ants_mean, [('epi', 'average_image')]),
        (ants_mean, ants_hmc, [('average_image', 'fixed_image')]),
        (inputnode, ants_hmc, [('epi', 'moving_image')]),
        (ants_mean, skullstrip_epi, [('average_image', 'in_file')]),
        (skullstrip_epi, dvars, [('mask_file', 'in_mask')]),
        (ants_hmc, dvars, [('warped_image', 'in_file')]),
        (dvars, concat, [('out_all', 'dvars')]),
        (concat, outputnode, [('combined_out', 'dvar_out')]),
        (ants_hmc, outputnode, [('warped_image', 'epi_hmc')]),
        (skullstrip_epi, outputnode, [('mask_file', 'epi_mask')]),
        (skullstrip_epi, ants_fd, [('mask_file', 'mask')]),
        (ants_hmc, ants_fd, [('composite_transform', 'moco')]),
        (ants_hmc, params, [('composite_transform', 'matrix')]),
        (params, frame_displace,  [('parameters', 'in_plots')]),
        (frame_displace, concat, [('out_file', 'frame_displace')]),
    ])

    ds_mask = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='ants_mask'),
        name='antsDerivativesEPImask'
    )
    ds_hmc = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='ants_hmc'),
        name='antsDerivativesEPIHMC'
    )
    ds_dvars = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='ants_dvar'),
        name='antsDerivativesEPIDVARS'
    )
    ds_par = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='ants_par'),
        name='antsDerivativesMotPar'
    )
    ds_fd = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='ants_fd'),
        name='antsDerivativesEPIFD'
    )
    workflow.connect([
        (inputnode, ds_mask, [('epi', 'source_file')]),
        (inputnode, ds_hmc, [('epi', 'source_file')]),
        (inputnode, ds_dvars, [('epi', 'source_file')]),
        (inputnode, ds_fd, [('epi', 'source_file')]),
        (inputnode, ds_par, [('epi', 'source_file')]),
        (skullstrip_epi, ds_mask, [('mask_file', 'in_file')]),
        (ants_hmc, ds_hmc, [('warped_image', 'in_file')]),
        (concat, ds_dvars, [('combined_out', 'in_file')]),
        (ants_fd, ds_fd, [('output', 'in_file')]),
        (params, ds_par, [('parameters', 'in_file')])
    ])
    return workflow

def test_fsl(name='test_mcflirt', settings=None):
    workflow = pe.Workflow(name=name)
    inputnode = pe.Node(niu.IdentityInterface(fields=['epi']), name='inputnode')
    outputnode = pe.Node(niu.IdentityInterface(
        fields=['epi_hmc', 'dvars_out', 'epi_mask']), name='outputnode')

    hmc = pe.Node(fsl.MCFLIRT(
        save_mats=True, save_plots=True, mean_vol=True), name='fslEPI_hmc')
    hmc.interface.estimated_memory_gb = settings["biggest_epi_file_size_gb"] * 3
    skullstrip_epi = pe.Node(ComputeEPIMask(generate_report=True, dilation=1),
                             name='skullstrip_epi')
    dvars = pe.Node(ComputeDVARS(save_all=True, remove_zerovariance=True),
                    name='fslDVARS')
    dvars.interface.estimated_memory_gb = settings[
                                              "biggest_epi_file_size_gb"] * 3

    frame_displace = pe.Node(FramewiseDisplacement(),
                             name="FramewiseDisplacement")
    frame_displace.interface.estimated_memory_gb = settings[
                                              "biggest_epi_file_size_gb"] * 3

    concat = pe.Node(
        utility.Function(
            function=_gather_confounds,
            input_names=['dvars', 'frame_displace'],
            output_names=['combined_out']
        ),
        name="ConcatConfounds"
    )

    workflow.connect([
        (inputnode, hmc, [('epi', 'in_file')]),
        (hmc, skullstrip_epi, [('mean_img', 'in_file')]),
        (skullstrip_epi, dvars, [('mask_file', 'in_mask')]),
        (hmc, dvars, [('out_file', 'in_file')]),
        (dvars, concat, [('out_all', 'dvars')]),
        (concat, outputnode, [('combined_out', 'dvars_out')]),
        (skullstrip_epi, outputnode, [('mask_file', 'epi_mask')]),
        (hmc, outputnode, [('out_file', 'epi_hmc')]),
        (hmc, frame_displace, [('par_file', 'in_plots')]),
        (frame_displace, concat, [('out_file', 'frame_displace')]),
    ])

    ds_mask = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='fsl_mask'),
        name='DerivativesEPImask'
    )
    ds_hmc = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='fsl_hmc'),
        name='DerivativesEPIHMC'
    )
    ds_dvars = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='fsl_dvar'),
        name='DerivativesEPIDVARS'
    )
    ds_fd = pe.Node(
        DerivativesDataSink(base_directory=settings['output_dir'],
                            suffix='fsl_fd'),
        name='DerivativesEPIFD'
    )

    workflow.connect([
        (inputnode, ds_mask, [('epi', 'source_file')]),
        (inputnode, ds_hmc, [('epi', 'source_file')]),
        (inputnode, ds_dvars, [('epi', 'source_file')]),
        (skullstrip_epi, ds_mask, [('mask_file', 'in_file')]),
        (hmc, ds_hmc, [('out_file', 'in_file')]),
        (concat, ds_dvars, [('combined_out', 'in_file')]),
    ])
    return workflow

def _first(inlist):
    if isinstance(inlist, (list, tuple)):
        inlist = _first(inlist[0])
    return inlist
