#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## TRC QUANTITATIVE EVALUATION                  ##
    ##################################################

    Evaluate 3D keypoint quality from a TRC file using four metrics:
      A. Bone length consistency (CV%)
      B. Trajectory smoothness (acceleration)
      C. Missing data (NaN rate)
      D. Left-right symmetry

    Single mode: evaluate one TRC file.
    Comparison mode: evaluate two TRC files and show before/after changes.

    Usage:
        trc_evaluate -i file.trc
        trc_evaluate -i before.trc after.trc
        trc_evaluate -i file.trc -o results.csv
'''


## INIT
import os
import argparse
import numpy as np
from pathlib import Path

from Pose2Sim.common import extract_trc_data


## CONSTANTS

# Bone connections for HALPE_26: (parent_marker, child_marker, display_name)
HALPE_26_BONES = [
    # Right leg
    ('Hip',       'RHip',      'Hip-RHip'),
    ('RHip',      'RKnee',     'R Thigh'),
    ('RKnee',     'RAnkle',    'R Shank'),
    ('RAnkle',    'RBigToe',   'R Foot'),
    ('RBigToe',   'RSmallToe', 'R Toe'),
    ('RAnkle',    'RHeel',     'R Heel'),
    # Left leg
    ('Hip',       'LHip',      'Hip-LHip'),
    ('LHip',      'LKnee',     'L Thigh'),
    ('LKnee',     'LAnkle',    'L Shank'),
    ('LAnkle',    'LBigToe',   'L Foot'),
    ('LBigToe',   'LSmallToe', 'L Toe'),
    ('LAnkle',    'LHeel',     'L Heel'),
    # Trunk
    ('Hip',       'Neck',      'Trunk'),
    ('Neck',      'Head',      'Neck-Head'),
    # Right arm
    ('Neck',      'RShoulder', 'Neck-RShoulder'),
    ('RShoulder', 'RElbow',    'R Upper Arm'),
    ('RElbow',    'RWrist',    'R Forearm'),
    # Left arm
    ('Neck',      'LShoulder', 'Neck-LShoulder'),
    ('LShoulder', 'LElbow',    'L Upper Arm'),
    ('LElbow',    'LWrist',    'L Forearm'),
]

# Symmetric bone pairs: (left_bone_name, right_bone_name, pair_display_name)
SYMMETRIC_BONE_PAIRS = [
    ('Hip-LHip',      'Hip-RHip',      'Hip'),
    ('L Thigh',       'R Thigh',       'Thigh'),
    ('L Shank',       'R Shank',       'Shank'),
    ('L Foot',        'R Foot',        'Foot'),
    ('L Toe',         'R Toe',         'Toe'),
    ('L Heel',        'R Heel',        'Heel'),
    ('Neck-LShoulder','Neck-RShoulder','Shoulder'),
    ('L Upper Arm',   'R Upper Arm',   'Upper Arm'),
    ('L Forearm',     'R Forearm',     'Forearm'),
]


## FUNCTIONS

def load_trc_as_marker_dict(trc_path):
    '''
    Load a TRC file and return marker data as a dictionary.

    INPUTS:
    - trc_path: str, path to TRC file

    OUTPUTS:
    - marker_names: list of str
    - time_arr: ndarray shape (n_frames,)
    - markers_3d: dict {marker_name: ndarray shape (n_frames, 3)}
    - fps: float
    '''

    marker_names, trc_data_np = extract_trc_data(trc_path)

    # Read FPS from header line 3
    with open(trc_path, 'r') as f:
        lines = f.readlines()
    fps = float(lines[2].split('\t')[0])

    time_arr = trc_data_np[:, 0]
    coords = trc_data_np[:, 1:]
    n_frames = len(time_arr)
    n_markers = len(marker_names)

    coords_3d = coords[:, :n_markers*3].reshape(n_frames, n_markers, 3)
    markers_3d = {name: coords_3d[:, i, :] for i, name in enumerate(marker_names)}

    return marker_names, time_arr, markers_3d, fps


def compute_bone_lengths(markers_3d, bones=None):
    '''
    Compute bone length statistics across all frames.

    INPUTS:
    - markers_3d: dict {marker_name: ndarray (n_frames, 3)}
    - bones: list of (parent, child, name) tuples. Default: HALPE_26_BONES

    OUTPUTS:
    - list of dict with keys: name, parent, child, mean, sd, cv, n_valid
    '''

    if bones is None:
        bones = HALPE_26_BONES

    results = []
    for parent, child, name in bones:
        if parent not in markers_3d or child not in markers_3d:
            continue

        p = markers_3d[parent]
        c = markers_3d[child]
        lengths = np.linalg.norm(c - p, axis=1)

        # Replace zero lengths with NaN (both markers missing at same location)
        lengths[lengths == 0.0] = np.nan

        n_valid = int(np.sum(~np.isnan(lengths)))
        if n_valid == 0:
            results.append({'name': name, 'parent': parent, 'child': child,
                            'mean': np.nan, 'sd': np.nan, 'cv': np.nan, 'n_valid': 0})
            continue

        mean_val = np.nanmean(lengths)
        sd_val = np.nanstd(lengths)
        cv_val = (sd_val / mean_val * 100) if mean_val > 0 else np.nan

        results.append({'name': name, 'parent': parent, 'child': child,
                        'mean': mean_val, 'sd': sd_val, 'cv': cv_val, 'n_valid': n_valid})

    return results


def compute_smoothness(markers_3d, marker_names, fps):
    '''
    Compute trajectory smoothness (acceleration) for each marker.

    INPUTS:
    - markers_3d: dict {marker_name: ndarray (n_frames, 3)}
    - marker_names: list of str
    - fps: float

    OUTPUTS:
    - list of dict with keys: name, accel_median, accel_p95, accel_median_si, accel_p95_si, n_valid
    '''

    results = []
    for name in marker_names:
        pos = markers_3d[name]  # (n_frames, 3)
        n_frames = pos.shape[0]

        if n_frames < 3:
            results.append({'name': name, 'accel_median': np.nan, 'accel_p95': np.nan,
                            'accel_median_si': np.nan, 'accel_p95_si': np.nan, 'n_valid': 0})
            continue

        # Second-order difference (acceleration in m/frame^2)
        accel = pos[2:] - 2 * pos[1:-1] + pos[:-2]
        accel_mag = np.linalg.norm(accel, axis=1)

        # Remove NaN
        valid = accel_mag[~np.isnan(accel_mag)]
        n_valid = len(valid)

        if n_valid == 0:
            results.append({'name': name, 'accel_median': np.nan, 'accel_p95': np.nan,
                            'accel_median_si': np.nan, 'accel_p95_si': np.nan, 'n_valid': 0})
            continue

        median_val = float(np.median(valid))
        p95_val = float(np.percentile(valid, 95))

        results.append({
            'name': name,
            'accel_median': median_val,
            'accel_p95': p95_val,
            'accel_median_si': median_val * fps * fps,
            'accel_p95_si': p95_val * fps * fps,
            'n_valid': n_valid,
        })

    return results


def compute_missing_data(markers_3d, marker_names):
    '''
    Compute NaN rate for each marker.

    INPUTS:
    - markers_3d: dict {marker_name: ndarray (n_frames, 3)}
    - marker_names: list of str

    OUTPUTS:
    - list of dict with keys: name, n_total, n_missing, missing_pct
    '''

    results = []
    for name in marker_names:
        pos = markers_3d[name]
        n_total = pos.shape[0]
        # A frame is missing if any of X, Y, Z is NaN
        missing_mask = np.any(np.isnan(pos), axis=1)
        n_missing = int(np.sum(missing_mask))
        missing_pct = n_missing / n_total * 100 if n_total > 0 else 0.0

        results.append({
            'name': name,
            'n_total': n_total,
            'n_missing': n_missing,
            'missing_pct': missing_pct,
        })

    return results


def compute_symmetry(bone_results, symmetric_pairs=None):
    '''
    Compare left-right symmetric bone pairs.

    INPUTS:
    - bone_results: list of dict from compute_bone_lengths()
    - symmetric_pairs: list of (left_name, right_name, pair_name). Default: SYMMETRIC_BONE_PAIRS

    OUTPUTS:
    - list of dict with keys: pair_name, left_name, right_name, left_mean, right_mean, diff_pct
    '''

    if symmetric_pairs is None:
        symmetric_pairs = SYMMETRIC_BONE_PAIRS

    bone_map = {r['name']: r for r in bone_results}
    results = []

    for left_name, right_name, pair_name in symmetric_pairs:
        if left_name not in bone_map or right_name not in bone_map:
            continue

        l_mean = bone_map[left_name]['mean']
        r_mean = bone_map[right_name]['mean']

        if np.isnan(l_mean) or np.isnan(r_mean):
            diff_pct = np.nan
        else:
            avg = (l_mean + r_mean) / 2
            diff_pct = abs(l_mean - r_mean) / avg * 100 if avg > 0 else np.nan

        results.append({
            'pair_name': pair_name,
            'left_name': left_name,
            'right_name': right_name,
            'left_mean': l_mean,
            'right_mean': r_mean,
            'diff_pct': diff_pct,
        })

    return results


def evaluate_single(trc_path):
    '''
    Evaluate a single TRC file with all four metrics.

    INPUTS:
    - trc_path: str, path to TRC file

    OUTPUTS:
    - dict with keys: trc_path, n_frames, n_markers, fps,
      bone_results, smooth_results, missing_results, symmetry_results, summary
    '''

    marker_names, time_arr, markers_3d, fps = load_trc_as_marker_dict(trc_path)
    n_frames = len(time_arr)
    n_markers = len(marker_names)

    bone_results = compute_bone_lengths(markers_3d)
    smooth_results = compute_smoothness(markers_3d, marker_names, fps)
    missing_results = compute_missing_data(markers_3d, marker_names)
    symmetry_results = compute_symmetry(bone_results)

    # Summary
    valid_cvs = [b['cv'] for b in bone_results if not np.isnan(b['cv'])]
    mean_cv = np.mean(valid_cvs) if valid_cvs else np.nan
    worst_bone = max(bone_results, key=lambda b: b['cv'] if not np.isnan(b['cv']) else -1) if bone_results else None
    worst_cv = worst_bone['cv'] if worst_bone and not np.isnan(worst_bone['cv']) else np.nan
    worst_bone_name = worst_bone['name'] if worst_bone else ''

    valid_p95s = [s['accel_p95'] for s in smooth_results if not np.isnan(s['accel_p95'])]
    mean_accel_p95 = np.mean(valid_p95s) if valid_p95s else np.nan

    total_frames = sum(m['n_total'] for m in missing_results)
    total_missing = sum(m['n_missing'] for m in missing_results)
    overall_nan_pct = total_missing / total_frames * 100 if total_frames > 0 else 0.0

    valid_diffs = [s['diff_pct'] for s in symmetry_results if not np.isnan(s['diff_pct'])]
    mean_lr_diff = np.mean(valid_diffs) if valid_diffs else np.nan

    return {
        'trc_path': trc_path,
        'n_frames': n_frames,
        'n_markers': n_markers,
        'fps': fps,
        'bone_results': bone_results,
        'smooth_results': smooth_results,
        'missing_results': missing_results,
        'symmetry_results': symmetry_results,
        'summary': {
            'mean_cv': mean_cv,
            'worst_bone': worst_bone_name,
            'worst_cv': worst_cv,
            'mean_accel_p95': mean_accel_p95,
            'overall_nan_pct': overall_nan_pct,
            'mean_lr_diff': mean_lr_diff,
        },
    }


def format_report(eval_result):
    '''
    Format a single evaluation result as a terminal report string.
    '''

    r = eval_result
    s = r['summary']
    lines = []

    lines.append('=== TRC Evaluation Report ===')
    lines.append(f"File: {os.path.basename(r['trc_path'])} | Frames: {r['n_frames']} | Markers: {r['n_markers']} | FPS: {r['fps']}")
    lines.append('')

    # A. Bone Length Consistency
    lines.append('--- A. Bone Length Consistency ---')
    lines.append(f"  {'':24s} {'Mean(m)':>8s} {'SD(m)':>8s} {'CV(%)':>8s}")
    for b in r['bone_results']:
        if np.isnan(b['cv']):
            lines.append(f"  {b['name']:24s} {'N/A':>8s} {'N/A':>8s} {'N/A':>8s}")
        else:
            lines.append(f"  {b['name']:24s} {b['mean']:8.4f} {b['sd']:8.4f} {b['cv']:7.1f}%")
    lines.append(f"  Summary: Mean CV = {s['mean_cv']:.1f}%")
    lines.append('')

    # B. Trajectory Smoothness
    lines.append('--- B. Trajectory Smoothness (m/frame^2) ---')
    lines.append(f"  {'':24s} {'Median':>10s} {'95%ile':>10s}")
    for sm in r['smooth_results']:
        if np.isnan(sm['accel_p95']):
            lines.append(f"  {sm['name']:24s} {'N/A':>10s} {'N/A':>10s}")
        else:
            lines.append(f"  {sm['name']:24s} {sm['accel_median']:10.4f} {sm['accel_p95']:10.4f}")
    lines.append(f"  Summary: Mean 95%ile = {s['mean_accel_p95']:.4f}")
    lines.append('')

    # C. Missing Data
    lines.append('--- C. Missing Data ---')
    lines.append(f"  {'':24s} {'NaN Rate':>10s}")
    for m in r['missing_results']:
        lines.append(f"  {m['name']:24s} {m['missing_pct']:9.1f}%")
    lines.append(f"  Summary: Overall = {s['overall_nan_pct']:.1f}%")
    lines.append('')

    # D. Left-Right Symmetry
    lines.append('--- D. Left-Right Symmetry ---')
    lines.append(f"  {'':24s} {'L(m)':>8s} {'R(m)':>8s} {'Diff(%)':>8s}")
    for sy in r['symmetry_results']:
        if np.isnan(sy['diff_pct']):
            lines.append(f"  {sy['pair_name']:24s} {'N/A':>8s} {'N/A':>8s} {'N/A':>8s}")
        else:
            lines.append(f"  {sy['pair_name']:24s} {sy['left_mean']:8.4f} {sy['right_mean']:8.4f} {sy['diff_pct']:7.1f}%")
    lines.append(f"  Summary: Mean L-R Diff = {s['mean_lr_diff']:.1f}%")
    lines.append('')

    # Overall Summary
    lines.append('=== Summary ===')
    lines.append(f"  Bone CV: {s['mean_cv']:.1f}%  |  Smoothness 95%ile: {s['mean_accel_p95']:.4f}  |  NaN: {s['overall_nan_pct']:.1f}%  |  L-R Diff: {s['mean_lr_diff']:.1f}%")

    return '\n'.join(lines)


def _verdict(before, after, lower_is_better=True):
    '''Return IMPROVED/WORSE/empty based on change direction.'''
    if np.isnan(before) or np.isnan(after):
        return ''
    if lower_is_better:
        if after < before:
            return 'IMPROVED'
        elif after > before:
            return 'WORSE'
    else:
        if after > before:
            return 'IMPROVED'
        elif after < before:
            return 'WORSE'
    return ''


def format_comparison_report(eval_a, eval_b):
    '''
    Format a comparison report between two evaluations.
    eval_a = before, eval_b = after.
    '''

    sa = eval_a['summary']
    sb = eval_b['summary']
    lines = []

    lines.append('=' * 80)
    lines.append('TRC Comparison Report')
    lines.append(f"File A (before): {os.path.basename(eval_a['trc_path'])}")
    lines.append(f"File B (after):  {os.path.basename(eval_b['trc_path'])}")
    lines.append('=' * 80)
    lines.append('')

    # A. Bone Length Consistency
    lines.append('--- A. Bone Length Consistency (CV%) ---')
    lines.append(f"  {'':24s} {'Before':>8s} {'After':>8s} {'Change':>8s}")
    bone_map_a = {b['name']: b for b in eval_a['bone_results']}
    bone_map_b = {b['name']: b for b in eval_b['bone_results']}
    all_bone_names = list(dict.fromkeys(
        [b['name'] for b in eval_a['bone_results']] + [b['name'] for b in eval_b['bone_results']]
    ))
    for name in all_bone_names:
        cv_a = bone_map_a[name]['cv'] if name in bone_map_a else np.nan
        cv_b = bone_map_b[name]['cv'] if name in bone_map_b else np.nan
        v = _verdict(cv_a, cv_b)
        if np.isnan(cv_a) and np.isnan(cv_b):
            continue
        cv_a_s = f"{cv_a:.1f}%" if not np.isnan(cv_a) else 'N/A'
        cv_b_s = f"{cv_b:.1f}%" if not np.isnan(cv_b) else 'N/A'
        change_s = f"{cv_b - cv_a:+.1f}%" if not (np.isnan(cv_a) or np.isnan(cv_b)) else ''
        lines.append(f"  {name:24s} {cv_a_s:>8s} {cv_b_s:>8s} {change_s:>8s}  {v}")
    v = _verdict(sa['mean_cv'], sb['mean_cv'])
    lines.append(f"  {'Summary: Mean CV':24s} {sa['mean_cv']:.1f}% -> {sb['mean_cv']:.1f}%  {sb['mean_cv']-sa['mean_cv']:+.1f}%  {v}")
    lines.append('')

    # B. Trajectory Smoothness
    lines.append('--- B. Trajectory Smoothness (95%ile, m/frame^2) ---')
    lines.append(f"  {'':24s} {'Before':>10s} {'After':>10s} {'Change':>8s}")
    smooth_map_a = {s['name']: s for s in eval_a['smooth_results']}
    smooth_map_b = {s['name']: s for s in eval_b['smooth_results']}
    all_smooth_names = list(dict.fromkeys(
        [s['name'] for s in eval_a['smooth_results']] + [s['name'] for s in eval_b['smooth_results']]
    ))
    for name in all_smooth_names:
        p95_a = smooth_map_a[name]['accel_p95'] if name in smooth_map_a else np.nan
        p95_b = smooth_map_b[name]['accel_p95'] if name in smooth_map_b else np.nan
        v = _verdict(p95_a, p95_b)
        if np.isnan(p95_a) and np.isnan(p95_b):
            continue
        a_s = f"{p95_a:.4f}" if not np.isnan(p95_a) else 'N/A'
        b_s = f"{p95_b:.4f}" if not np.isnan(p95_b) else 'N/A'
        if not (np.isnan(p95_a) or np.isnan(p95_b)) and p95_a != 0:
            change_pct = (p95_b - p95_a) / p95_a * 100
            change_s = f"{change_pct:+.1f}%"
        else:
            change_s = ''
        lines.append(f"  {name:24s} {a_s:>10s} {b_s:>10s} {change_s:>8s}  {v}")
    v = _verdict(sa['mean_accel_p95'], sb['mean_accel_p95'])
    if sa['mean_accel_p95'] != 0:
        ch = (sb['mean_accel_p95'] - sa['mean_accel_p95']) / sa['mean_accel_p95'] * 100
        lines.append(f"  {'Summary: Mean 95%ile':24s} {sa['mean_accel_p95']:.4f} -> {sb['mean_accel_p95']:.4f}  {ch:+.1f}%  {v}")
    else:
        lines.append(f"  {'Summary: Mean 95%ile':24s} {sa['mean_accel_p95']:.4f} -> {sb['mean_accel_p95']:.4f}  {v}")
    lines.append('')

    # C. Missing Data
    lines.append('--- C. Missing Data (NaN%) ---')
    lines.append(f"  {'':24s} {'Before':>8s} {'After':>8s} {'Change':>8s}")
    miss_map_a = {m['name']: m for m in eval_a['missing_results']}
    miss_map_b = {m['name']: m for m in eval_b['missing_results']}
    all_miss_names = list(dict.fromkeys(
        [m['name'] for m in eval_a['missing_results']] + [m['name'] for m in eval_b['missing_results']]
    ))
    for name in all_miss_names:
        pct_a = miss_map_a[name]['missing_pct'] if name in miss_map_a else np.nan
        pct_b = miss_map_b[name]['missing_pct'] if name in miss_map_b else np.nan
        v = _verdict(pct_a, pct_b)
        a_s = f"{pct_a:.1f}%" if not np.isnan(pct_a) else 'N/A'
        b_s = f"{pct_b:.1f}%" if not np.isnan(pct_b) else 'N/A'
        change_s = f"{pct_b - pct_a:+.1f}%" if not (np.isnan(pct_a) or np.isnan(pct_b)) else ''
        lines.append(f"  {name:24s} {a_s:>8s} {b_s:>8s} {change_s:>8s}  {v}")
    v = _verdict(sa['overall_nan_pct'], sb['overall_nan_pct'])
    lines.append(f"  {'Summary: Overall':24s} {sa['overall_nan_pct']:.1f}% -> {sb['overall_nan_pct']:.1f}%  {sb['overall_nan_pct']-sa['overall_nan_pct']:+.1f}%  {v}")
    lines.append('')

    # D. Left-Right Symmetry
    lines.append('--- D. Left-Right Symmetry (Diff%) ---')
    lines.append(f"  {'':24s} {'Before':>8s} {'After':>8s} {'Change':>8s}")
    sym_map_a = {s['pair_name']: s for s in eval_a['symmetry_results']}
    sym_map_b = {s['pair_name']: s for s in eval_b['symmetry_results']}
    all_sym_names = list(dict.fromkeys(
        [s['pair_name'] for s in eval_a['symmetry_results']] + [s['pair_name'] for s in eval_b['symmetry_results']]
    ))
    for name in all_sym_names:
        d_a = sym_map_a[name]['diff_pct'] if name in sym_map_a else np.nan
        d_b = sym_map_b[name]['diff_pct'] if name in sym_map_b else np.nan
        v = _verdict(d_a, d_b)
        a_s = f"{d_a:.1f}%" if not np.isnan(d_a) else 'N/A'
        b_s = f"{d_b:.1f}%" if not np.isnan(d_b) else 'N/A'
        change_s = f"{d_b - d_a:+.1f}%" if not (np.isnan(d_a) or np.isnan(d_b)) else ''
        lines.append(f"  {name:24s} {a_s:>8s} {b_s:>8s} {change_s:>8s}  {v}")
    v = _verdict(sa['mean_lr_diff'], sb['mean_lr_diff'])
    lines.append(f"  {'Summary: Mean Diff':24s} {sa['mean_lr_diff']:.1f}% -> {sb['mean_lr_diff']:.1f}%  {sb['mean_lr_diff']-sa['mean_lr_diff']:+.1f}%  {v}")
    lines.append('')

    # Overall Summary
    lines.append('=' * 80)
    lines.append('Overall Summary')
    lines.append(f"  {'':24s} {'Before':>14s} {'After':>14s}")
    v_cv = _verdict(sa['mean_cv'], sb['mean_cv'])
    v_sm = _verdict(sa['mean_accel_p95'], sb['mean_accel_p95'])
    v_na = _verdict(sa['overall_nan_pct'], sb['overall_nan_pct'])
    v_lr = _verdict(sa['mean_lr_diff'], sb['mean_lr_diff'])
    lines.append(f"  {'Bone CV (mean):':24s} {sa['mean_cv']:13.1f}% {sb['mean_cv']:13.1f}%   {v_cv}")
    lines.append(f"  {'Smooth 95%ile:':24s} {sa['mean_accel_p95']:14.4f} {sb['mean_accel_p95']:14.4f}   {v_sm}")
    lines.append(f"  {'NaN rate:':24s} {sa['overall_nan_pct']:13.1f}% {sb['overall_nan_pct']:13.1f}%   {v_na}")
    lines.append(f"  {'L-R Diff (mean):':24s} {sa['mean_lr_diff']:13.1f}% {sb['mean_lr_diff']:13.1f}%   {v_lr}")
    lines.append('=' * 80)

    return '\n'.join(lines)


def save_csv(eval_result, csv_path):
    '''
    Save single evaluation result to CSV.
    Format: metric,item,value,unit,detail
    '''

    r = eval_result
    s = r['summary']
    lines = ['metric,item,value,unit,detail']

    for b in r['bone_results']:
        if np.isnan(b['cv']):
            continue
        lines.append(f"bone_cv,{b['name']},{b['cv']:.1f},%,mean={b['mean']:.4f} sd={b['sd']:.4f}")

    for sm in r['smooth_results']:
        if np.isnan(sm['accel_p95']):
            continue
        lines.append(f"smoothness_p95,{sm['name']},{sm['accel_p95']:.4f},m/frame^2,median={sm['accel_median']:.4f}")

    for m in r['missing_results']:
        lines.append(f"missing,{m['name']},{m['missing_pct']:.1f},%,{m['n_missing']}/{m['n_total']}")

    for sy in r['symmetry_results']:
        if np.isnan(sy['diff_pct']):
            continue
        lines.append(f"symmetry,{sy['pair_name']},{sy['diff_pct']:.1f},%,L={sy['left_mean']:.4f} R={sy['right_mean']:.4f}")

    lines.append(f"summary,bone_cv_mean,{s['mean_cv']:.1f},%,")
    lines.append(f"summary,smoothness_p95_mean,{s['mean_accel_p95']:.4f},m/frame^2,")
    lines.append(f"summary,missing_overall,{s['overall_nan_pct']:.1f},%,")
    lines.append(f"summary,symmetry_mean,{s['mean_lr_diff']:.1f},%,")

    with open(csv_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def save_comparison_csv(eval_a, eval_b, csv_path):
    '''
    Save comparison result to CSV.
    Format: metric,item,before,after,change,unit,verdict
    '''

    sa = eval_a['summary']
    sb = eval_b['summary']
    lines = ['metric,item,before,after,change,unit,verdict']

    # Bone CV
    bone_map_a = {b['name']: b for b in eval_a['bone_results']}
    bone_map_b = {b['name']: b for b in eval_b['bone_results']}
    all_bones = list(dict.fromkeys(
        [b['name'] for b in eval_a['bone_results']] + [b['name'] for b in eval_b['bone_results']]
    ))
    for name in all_bones:
        cv_a = bone_map_a[name]['cv'] if name in bone_map_a else np.nan
        cv_b = bone_map_b[name]['cv'] if name in bone_map_b else np.nan
        if np.isnan(cv_a) and np.isnan(cv_b):
            continue
        v = _verdict(cv_a, cv_b)
        change = cv_b - cv_a if not (np.isnan(cv_a) or np.isnan(cv_b)) else np.nan
        change_s = f"{change:+.1f}" if not np.isnan(change) else ''
        lines.append(f"bone_cv,{name},{cv_a:.1f},{cv_b:.1f},{change_s},%,{v}")

    # Smoothness
    smooth_map_a = {s['name']: s for s in eval_a['smooth_results']}
    smooth_map_b = {s['name']: s for s in eval_b['smooth_results']}
    all_smooth = list(dict.fromkeys(
        [s['name'] for s in eval_a['smooth_results']] + [s['name'] for s in eval_b['smooth_results']]
    ))
    for name in all_smooth:
        p_a = smooth_map_a[name]['accel_p95'] if name in smooth_map_a else np.nan
        p_b = smooth_map_b[name]['accel_p95'] if name in smooth_map_b else np.nan
        if np.isnan(p_a) and np.isnan(p_b):
            continue
        v = _verdict(p_a, p_b)
        change = p_b - p_a if not (np.isnan(p_a) or np.isnan(p_b)) else np.nan
        change_s = f"{change:+.4f}" if not np.isnan(change) else ''
        lines.append(f"smoothness_p95,{name},{p_a:.4f},{p_b:.4f},{change_s},m/frame^2,{v}")

    # Missing
    miss_map_a = {m['name']: m for m in eval_a['missing_results']}
    miss_map_b = {m['name']: m for m in eval_b['missing_results']}
    all_miss = list(dict.fromkeys(
        [m['name'] for m in eval_a['missing_results']] + [m['name'] for m in eval_b['missing_results']]
    ))
    for name in all_miss:
        pct_a = miss_map_a[name]['missing_pct'] if name in miss_map_a else np.nan
        pct_b = miss_map_b[name]['missing_pct'] if name in miss_map_b else np.nan
        v = _verdict(pct_a, pct_b)
        change = pct_b - pct_a if not (np.isnan(pct_a) or np.isnan(pct_b)) else np.nan
        change_s = f"{change:+.1f}" if not np.isnan(change) else ''
        lines.append(f"missing,{name},{pct_a:.1f},{pct_b:.1f},{change_s},%,{v}")

    # Symmetry
    sym_map_a = {s['pair_name']: s for s in eval_a['symmetry_results']}
    sym_map_b = {s['pair_name']: s for s in eval_b['symmetry_results']}
    all_sym = list(dict.fromkeys(
        [s['pair_name'] for s in eval_a['symmetry_results']] + [s['pair_name'] for s in eval_b['symmetry_results']]
    ))
    for name in all_sym:
        d_a = sym_map_a[name]['diff_pct'] if name in sym_map_a else np.nan
        d_b = sym_map_b[name]['diff_pct'] if name in sym_map_b else np.nan
        v = _verdict(d_a, d_b)
        change = d_b - d_a if not (np.isnan(d_a) or np.isnan(d_b)) else np.nan
        change_s = f"{change:+.1f}" if not np.isnan(change) else ''
        lines.append(f"symmetry,{name},{d_a:.1f},{d_b:.1f},{change_s},%,{v}")

    # Summary
    def _sum_line(metric, item, ba, bb, unit):
        v = _verdict(ba, bb)
        change = bb - ba if not (np.isnan(ba) or np.isnan(bb)) else np.nan
        if unit == 'm/frame^2':
            change_s = f"{change:+.4f}" if not np.isnan(change) else ''
            return f"summary,{item},{ba:.4f},{bb:.4f},{change_s},{unit},{v}"
        else:
            change_s = f"{change:+.1f}" if not np.isnan(change) else ''
            return f"summary,{item},{ba:.1f},{bb:.1f},{change_s},{unit},{v}"

    lines.append(_sum_line('summary', 'bone_cv_mean', sa['mean_cv'], sb['mean_cv'], '%'))
    lines.append(_sum_line('summary', 'smoothness_p95_mean', sa['mean_accel_p95'], sb['mean_accel_p95'], 'm/frame^2'))
    lines.append(_sum_line('summary', 'missing_overall', sa['overall_nan_pct'], sb['overall_nan_pct'], '%'))
    lines.append(_sum_line('summary', 'symmetry_mean', sa['mean_lr_diff'], sb['mean_lr_diff'], '%'))

    with open(csv_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def trc_evaluate_func(**args):
    '''
    Orchestrator: run single or comparison evaluation.

    INPUTS:
    - input: list of str, TRC file paths (1 or 2)
    - output: str or None, output CSV path

    OUTPUTS:
    - Single mode: dict (evaluate_single result)
    - Comparison mode: tuple of (dict, dict)
    '''

    input_files = args.get('input', [])
    output_path = args.get('output', None)

    if len(input_files) == 1:
        # Single mode
        eval_result = evaluate_single(input_files[0])
        print(format_report(eval_result))

        if output_path is None:
            stem = Path(input_files[0]).stem
            output_path = str(Path(input_files[0]).parent / f"{stem}_evaluation.csv")
        save_csv(eval_result, output_path)
        print(f"\nCSV saved: {output_path}")

        return eval_result

    elif len(input_files) == 2:
        # Comparison mode
        eval_a = evaluate_single(input_files[0])
        eval_b = evaluate_single(input_files[1])
        print(format_comparison_report(eval_a, eval_b))

        if output_path is None:
            stem_a = Path(input_files[0]).stem
            stem_b = Path(input_files[1]).stem
            output_path = str(Path(input_files[0]).parent / f"{stem_a}_vs_{stem_b}_comparison.csv")
        save_comparison_csv(eval_a, eval_b, output_path)
        print(f"\nCSV saved: {output_path}")

        return eval_a, eval_b

    else:
        raise ValueError(f"Expected 1 or 2 input files, got {len(input_files)}")


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate 3D keypoint quality from TRC files. '
                    'Single mode (1 file): compute bone length consistency, smoothness, missing data, and symmetry. '
                    'Comparison mode (2 files): compare before/after metrics.')
    parser.add_argument('-i', '--input', required=True, nargs='+',
                        help='TRC file path(s). 1 file: single evaluation, 2 files: comparison mode.')
    parser.add_argument('-o', '--output', required=False, default=None,
                        help='Output CSV path. Default: auto-named in same directory as input.')

    args = vars(parser.parse_args())
    trc_evaluate_func(**args)


if __name__ == '__main__':
    main()
