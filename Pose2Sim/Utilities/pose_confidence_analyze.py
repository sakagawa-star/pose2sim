#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## 2D KEYPOINT CONFIDENCE ANALYSIS              ##
    ##################################################

    Analyze 2D pose estimation confidence scores across cameras and keypoints.
    Identifies low-confidence patterns that may degrade 3D triangulation quality.

    Analysis 1: Per-camera, per-keypoint confidence statistics (mean, median, percentiles, etc.)
    Analysis 2: Confidence band distribution and threshold simulation.

    Usage:
        pose_confidence_analyze -p /path/to/pose_dir
        pose_confidence_analyze -p /path/to/pose_dir -t 0.5 -o /path/to/output
        pose_confidence_analyze -p /path/to/pose_dir --no-plot
'''


## INIT
import os
import json
import argparse
import csv
import numpy as np
from pathlib import Path


## CONSTANTS

HALPE_26_NAMES = [
    'Nose', 'LEye', 'REye', 'LEar', 'REar',
    'LShoulder', 'RShoulder', 'LElbow', 'RElbow', 'LWrist', 'RWrist',
    'LHip', 'RHip', 'LKnee', 'RKnee', 'LAnkle', 'RAnkle',
    'Head', 'Neck', 'Hip',
    'LBigToe', 'RBigToe', 'LSmallToe', 'RSmallToe', 'LHeel', 'RHeel'
]

CONFIDENCE_BANDS = [
    (0.0, 0.4, 'low'),
    (0.4, 0.6, 'danger'),
    (0.6, 0.8, 'medium'),
    (0.8, 1.0, 'high'),
    (1.0, float('inf'), 'very_high'),
]

BAND_LABELS = {
    'low': '<0.4',
    'danger': '0.4-0.6',
    'medium': '0.6-0.8',
    'high': '0.8-1.0',
    'very_high': '>1.0',
}


## FUNCTIONS

def load_camera_data(cam_dir):
    '''Load confidence values from all JSON files in a camera directory.

    Parameters
    ----------
    cam_dir : Path
        Directory containing per-frame JSON files.

    Returns
    -------
    np.ndarray
        Shape (n_frames, 26) confidence matrix.
    '''
    json_files = sorted(cam_dir.glob('*.json'))
    if not json_files:
        raise FileNotFoundError(f'No JSON files found in {cam_dir}')

    confidence_list = []
    for jf in json_files:
        with open(jf) as f:
            data = json.load(f)
        if not data.get('people'):
            confidence_list.append(np.full(26, np.nan))
            continue
        kps = data['people'][0]['pose_keypoints_2d']
        conf = [kps[i*3 + 2] for i in range(26)]
        confidence_list.append(conf)

    return np.array(confidence_list)


def load_pose_data(pose_dir):
    '''Load confidence data from all cameras in a pose directory.

    Parameters
    ----------
    pose_dir : Path
        Directory containing cam*_json subdirectories.

    Returns
    -------
    dict[str, np.ndarray]
        {camera_name: confidence_matrix} sorted by camera name.
    '''
    pose_dir = Path(pose_dir)
    cam_dirs = sorted(pose_dir.glob('cam*_json'))
    if not cam_dirs:
        raise FileNotFoundError(f'No cam*_json directories found in {pose_dir}')

    confidence_data = {}
    for cam_dir in cam_dirs:
        cam_name = cam_dir.name.replace('_json', '')
        confidence_data[cam_name] = load_camera_data(cam_dir)

    return confidence_data


def compute_statistics(confidence_data, threshold=0.4):
    '''Compute per-camera, per-keypoint confidence statistics.

    Parameters
    ----------
    confidence_data : dict[str, np.ndarray]
    threshold : float

    Returns
    -------
    dict
        {cam: {kp_idx: {stat_name: value}}}
    '''
    stats = {}
    for cam, data in confidence_data.items():
        stats[cam] = {}
        for kp_idx in range(data.shape[1]):
            col = data[:, kp_idx]
            valid = col[~np.isnan(col)]
            if len(valid) == 0:
                stats[cam][kp_idx] = {k: np.nan for k in
                    ['mean', 'median', 'std', 'min', 'max',
                     'p5', 'p25', 'p75', 'p95', 'below_threshold_rate']}
                continue
            stats[cam][kp_idx] = {
                'mean': float(np.mean(valid)),
                'median': float(np.median(valid)),
                'std': float(np.std(valid)),
                'min': float(np.min(valid)),
                'max': float(np.max(valid)),
                'p5': float(np.percentile(valid, 5)),
                'p25': float(np.percentile(valid, 25)),
                'p75': float(np.percentile(valid, 75)),
                'p95': float(np.percentile(valid, 95)),
                'below_threshold_rate': float(np.sum(valid < threshold) / len(valid)),
            }
    return stats


def compute_band_distribution(confidence_data, bands=None):
    '''Compute confidence band distribution per camera and keypoint.

    Parameters
    ----------
    confidence_data : dict[str, np.ndarray]
    bands : list of (low, high, name) tuples

    Returns
    -------
    dict
        {cam: {kp_idx: {band_name: {'count': int, 'rate': float}}}}
    '''
    if bands is None:
        bands = CONFIDENCE_BANDS

    dist = {}
    for cam, data in confidence_data.items():
        dist[cam] = {}
        for kp_idx in range(data.shape[1]):
            col = data[:, kp_idx]
            valid = col[~np.isnan(col)]
            n = len(valid)
            dist[cam][kp_idx] = {}
            for low, high, name in bands:
                if name == 'high':
                    count = int(np.sum((valid >= low) & (valid <= high)))
                else:
                    count = int(np.sum((valid >= low) & (valid < high)))
                dist[cam][kp_idx][name] = {
                    'count': count,
                    'rate': count / n if n > 0 else 0.0,
                }
    return dist


def simulate_threshold(confidence_data, thresholds=None):
    '''Simulate the effect of raising the confidence threshold.

    Parameters
    ----------
    confidence_data : dict[str, np.ndarray]
    thresholds : list of float

    Returns
    -------
    dict
        {threshold: {cam: {kp_idx: exclusion_rate}}}
    '''
    if thresholds is None:
        thresholds = [0.4, 0.5, 0.6]

    sim = {}
    for th in thresholds:
        sim[th] = {}
        for cam, data in confidence_data.items():
            sim[th][cam] = {}
            for kp_idx in range(data.shape[1]):
                col = data[:, kp_idx]
                valid = col[~np.isnan(col)]
                n = len(valid)
                sim[th][cam][kp_idx] = float(np.sum(valid < th) / n) if n > 0 else 0.0
    return sim


def format_report(confidence_data, statistics, band_dist, threshold_sim, threshold):
    '''Format analysis results as a console report string.

    Parameters
    ----------
    confidence_data : dict[str, np.ndarray]
    statistics : dict
    band_dist : dict
    threshold_sim : dict
    threshold : float

    Returns
    -------
    str
    '''
    cameras = sorted(statistics.keys())
    n_kp = 26
    total_frames = sum(len(d) for d in confidence_data.values())

    lines = []
    lines.append('=== 2D Keypoint Confidence Analysis ===')
    lines.append(f'Cameras: {len(cameras)} ({", ".join(cameras)})')
    lines.append(f'Total frames: {total_frames}')
    lines.append(f'Threshold: {threshold}')
    lines.append('')

    # Analysis 1: Mean confidence table
    lines.append('--- Analysis 1: Mean Confidence per Camera x Keypoint ---')
    header = f'{"Keypoint":<14}' + ''.join(f'{c:>8}' for c in cameras) + f'{"avg":>8}'
    lines.append(header)
    lines.append('-' * len(header))

    all_means = []
    for kp_idx in range(n_kp):
        cam_means = []
        for cam in cameras:
            cam_means.append(statistics[cam][kp_idx]['mean'])
        avg = np.nanmean(cam_means)
        all_means.append((kp_idx, avg))
        row = f'{HALPE_26_NAMES[kp_idx]:<14}'
        for m in cam_means:
            row += f'{m:>8.3f}'
        row += f'{avg:>8.3f}'
        lines.append(row)

    lines.append('')

    # Problem keypoints (bottom 25%)
    all_means_sorted = sorted(all_means, key=lambda x: x[1])
    n_problem = max(1, n_kp // 4)
    problem_kps = all_means_sorted[:n_problem]
    lines.append(f'--- Low Confidence Keypoints (bottom {n_problem}) ---')
    for kp_idx, avg in problem_kps:
        detail = '  '.join(f'{cam}={statistics[cam][kp_idx]["mean"]:.3f}' for cam in cameras)
        lines.append(f'  {HALPE_26_NAMES[kp_idx]:<14} avg={avg:.3f}  ({detail})')
    lines.append('')

    # Analysis 2: Band distribution (camera-level summary)
    lines.append('--- Analysis 2: Confidence Band Distribution (per camera, all keypoints) ---')
    band_names = [b[2] for b in CONFIDENCE_BANDS]
    header2 = f'{"Camera":<8}' + ''.join(f'{BAND_LABELS[b]:>10}' for b in band_names)
    lines.append(header2)
    lines.append('-' * len(header2))

    for cam in cameras:
        band_totals = {b: 0 for b in band_names}
        total = 0
        for kp_idx in range(n_kp):
            for b in band_names:
                band_totals[b] += band_dist[cam][kp_idx][b]['count']
                total += band_dist[cam][kp_idx][b]['count']
        row = f'{cam:<8}'
        for b in band_names:
            rate = band_totals[b] / total * 100 if total > 0 else 0
            row += f'{rate:>9.1f}%'
        lines.append(row)

    lines.append('')

    # Danger zone hot spots
    lines.append('--- Danger Zone (0.4-0.6) Hot Spots (top 10) ---')
    danger_spots = []
    for cam in cameras:
        for kp_idx in range(n_kp):
            rate = band_dist[cam][kp_idx]['danger']['rate']
            if rate > 0:
                danger_spots.append((cam, kp_idx, rate))
    danger_spots.sort(key=lambda x: -x[2])
    for cam, kp_idx, rate in danger_spots[:10]:
        lines.append(f'  {cam}:{HALPE_26_NAMES[kp_idx]:<14} {rate*100:>5.1f}%')

    lines.append('')

    # Threshold simulation
    thresholds_sorted = sorted(threshold_sim.keys())
    base_th = thresholds_sorted[0] if thresholds_sorted else threshold
    lines.append('--- Threshold Simulation ---')
    for th in thresholds_sorted:
        if th == base_th:
            continue
        row_parts = []
        for cam in cameras:
            base_rates = [threshold_sim[base_th][cam][kp] for kp in range(n_kp)]
            new_rates = [threshold_sim[th][cam][kp] for kp in range(n_kp)]
            base_avg = np.mean(base_rates)
            new_avg = np.mean(new_rates)
            diff = new_avg - base_avg
            row_parts.append(f'{cam}: +{diff*100:.1f}%')
        lines.append(f'  {base_th} -> {th}  additional exclusion:  {", ".join(row_parts)}')

    lines.append('')
    return '\n'.join(lines)


def save_csv(statistics, band_dist, output_dir):
    '''Save statistics and band distribution to CSV files.

    Parameters
    ----------
    statistics : dict
    band_dist : dict
    output_dir : Path
    '''
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Statistics CSV
    stats_path = output_dir / 'confidence_statistics.csv'
    with open(stats_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['camera', 'keypoint', 'mean', 'median', 'std', 'min', 'max',
                         'p5', 'p25', 'p75', 'p95', 'below_threshold_rate'])
        for cam in sorted(statistics.keys()):
            for kp_idx in range(len(HALPE_26_NAMES)):
                s = statistics[cam][kp_idx]
                writer.writerow([
                    cam, HALPE_26_NAMES[kp_idx],
                    f'{s["mean"]:.4f}', f'{s["median"]:.4f}', f'{s["std"]:.4f}',
                    f'{s["min"]:.4f}', f'{s["max"]:.4f}',
                    f'{s["p5"]:.4f}', f'{s["p25"]:.4f}', f'{s["p75"]:.4f}', f'{s["p95"]:.4f}',
                    f'{s["below_threshold_rate"]:.4f}',
                ])
    print(f'Statistics CSV saved: {stats_path}')

    # Band distribution CSV
    band_path = output_dir / 'confidence_band_distribution.csv'
    band_names = [b[2] for b in CONFIDENCE_BANDS]
    with open(band_path, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ['camera', 'keypoint']
        for b in band_names:
            header.extend([f'{b}_count', f'{b}_rate'])
        writer.writerow(header)
        for cam in sorted(band_dist.keys()):
            for kp_idx in range(len(HALPE_26_NAMES)):
                row = [cam, HALPE_26_NAMES[kp_idx]]
                for b in band_names:
                    d = band_dist[cam][kp_idx][b]
                    row.extend([d['count'], f'{d["rate"]:.4f}'])
                writer.writerow(row)
    print(f'Band distribution CSV saved: {band_path}')


def save_heatmaps(statistics, band_dist, output_dir):
    '''Save heatmap images for mean confidence and danger zone rate.

    Parameters
    ----------
    statistics : dict
    band_dist : dict
    output_dir : Path
    '''
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cameras = sorted(statistics.keys())
    n_kp = len(HALPE_26_NAMES)

    # Heatmap 1: Mean confidence
    mean_matrix = np.zeros((n_kp, len(cameras)))
    for j, cam in enumerate(cameras):
        for i in range(n_kp):
            mean_matrix[i, j] = statistics[cam][i]['mean']

    fig, ax = plt.subplots(figsize=(6, 12))
    im = ax.imshow(mean_matrix, cmap='coolwarm', aspect='auto', vmin=0.4, vmax=1.0)
    ax.set_xticks(range(len(cameras)))
    ax.set_xticklabels(cameras)
    ax.set_yticks(range(n_kp))
    ax.set_yticklabels(HALPE_26_NAMES, fontsize=8)
    ax.set_title('Mean Confidence per Camera x Keypoint')
    for i in range(n_kp):
        for j in range(len(cameras)):
            ax.text(j, i, f'{mean_matrix[i,j]:.2f}', ha='center', va='center', fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.6)
    plt.tight_layout()
    path1 = output_dir / 'heatmap_mean_confidence.png'
    fig.savefig(path1, dpi=150)
    plt.close(fig)
    print(f'Heatmap saved: {path1}')

    # Heatmap 2: Danger zone rate
    danger_matrix = np.zeros((n_kp, len(cameras)))
    for j, cam in enumerate(cameras):
        for i in range(n_kp):
            danger_matrix[i, j] = band_dist[cam][i]['danger']['rate'] * 100

    fig, ax = plt.subplots(figsize=(6, 12))
    im = ax.imshow(danger_matrix, cmap='Reds', aspect='auto', vmin=0, vmax=max(danger_matrix.max(), 1))
    ax.set_xticks(range(len(cameras)))
    ax.set_xticklabels(cameras)
    ax.set_yticks(range(n_kp))
    ax.set_yticklabels(HALPE_26_NAMES, fontsize=8)
    ax.set_title('Danger Zone (0.4-0.6) Rate [%]')
    for i in range(n_kp):
        for j in range(len(cameras)):
            ax.text(j, i, f'{danger_matrix[i,j]:.1f}', ha='center', va='center', fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.6)
    plt.tight_layout()
    path2 = output_dir / 'heatmap_danger_zone_rate.png'
    fig.savefig(path2, dpi=150)
    plt.close(fig)
    print(f'Heatmap saved: {path2}')


def analyze_confidence(pose_dir, threshold=0.4, output=None, no_plot=False):
    '''Main orchestrator for confidence analysis.

    Parameters
    ----------
    pose_dir : str or Path
    threshold : float
    output : str or Path or None
    no_plot : bool

    Returns
    -------
    dict
        {'statistics': ..., 'band_distribution': ..., 'threshold_simulation': ...}
    '''
    pose_dir = Path(pose_dir)
    if output is None:
        output_dir = pose_dir / 'confidence_analysis'
    else:
        output_dir = Path(output)

    print(f'Loading pose data from {pose_dir} ...')
    confidence_data = load_pose_data(pose_dir)
    for cam, data in confidence_data.items():
        print(f'  {cam}: {data.shape[0]} frames')

    statistics = compute_statistics(confidence_data, threshold)
    band_dist = compute_band_distribution(confidence_data)

    thresholds = sorted(set([threshold, 0.4, 0.5, 0.6]))
    threshold_sim = simulate_threshold(confidence_data, thresholds)

    report = format_report(confidence_data, statistics, band_dist, threshold_sim, threshold)
    print(report)

    save_csv(statistics, band_dist, output_dir)

    if not no_plot:
        save_heatmaps(statistics, band_dist, output_dir)

    return {
        'statistics': statistics,
        'band_distribution': band_dist,
        'threshold_simulation': threshold_sim,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Analyze 2D pose estimation confidence scores across cameras and keypoints. '
                    'Identifies low-confidence patterns that may degrade 3D triangulation quality.')
    parser.add_argument('-p', '--pose-dir', required=True,
                        help='Pose directory path containing cam*_json subdirectories.')
    parser.add_argument('-t', '--threshold', type=float, default=0.4,
                        help='Current confidence threshold (default: 0.4).')
    parser.add_argument('-o', '--output', default=None,
                        help='Output directory path. Default: <pose_dir>/confidence_analysis/')
    parser.add_argument('--no-plot', action='store_true',
                        help='Skip heatmap image generation.')

    args = vars(parser.parse_args())
    analyze_confidence(**args)


if __name__ == '__main__':
    main()
