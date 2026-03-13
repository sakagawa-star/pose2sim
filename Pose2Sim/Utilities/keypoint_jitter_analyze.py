#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## 2D KEYPOINT JITTER ANALYSIS                  ##
    ##################################################

    Analyze frame-to-frame keypoint displacement anomalies (jitter) in 2D pose estimation outputs.
    Detects jitter events where displacement exceeds median * multiplier, classifies causes
    (out-of-frame, small BB, low confidence, other), and generates reports.

    Usage:
        keypoint_jitter_analyze -p /path/to/pose_dir
        keypoint_jitter_analyze -p /path/to/pose_dir --multiplier 5.0 -o /path/to/output
        keypoint_jitter_analyze -p /path/to/pose_dir --no-plot
'''


## INIT
import os
import json
import argparse
import csv
import numpy as np
from pathlib import Path
from glob import glob
from tqdm import tqdm


## CONSTANTS

HALPE_26_NAMES = [
    'Nose', 'LEye', 'REye', 'LEar', 'REar',
    'LShoulder', 'RShoulder', 'LElbow', 'RElbow', 'LWrist', 'RWrist',
    'LHip', 'RHip', 'LKnee', 'RKnee', 'LAnkle', 'RAnkle',
    'Head', 'Neck', 'Hip',
    'LBigToe', 'RBigToe', 'LSmallToe', 'RSmallToe', 'LHeel', 'RHeel'
]

CONF_THRESHOLD = 0.1
DEFAULT_MULTIPLIER = 5.0
DEFAULT_IMAGE_SIZE = (1920, 1080)
EDGE_MARGIN = 10  # pixels


## FUNCTIONS

def _select_person(people, prev_kp):
    '''Select the best person from a list of detected people.

    When multiple people are detected, selects the person closest to the
    previous frame's keypoints. Falls back to the person with the most
    valid keypoints if no previous frame is available.

    Parameters
    ----------
    people : list
        List of people dicts from OpenPose JSON.
    prev_kp : np.ndarray or None
        Previous frame's keypoints, shape (26, 3). None if first frame.

    Returns
    -------
    np.ndarray
        Shape (26, 3) keypoints of the selected person.
    '''
    valid_people = []
    for person in people:
        kps = person.get('pose_keypoints_2d', [])
        if len(kps) < 26 * 3:
            continue
        kp = np.array(kps).reshape(26, 3)
        n_valid = np.sum((kp[:, 2] > CONF_THRESHOLD) & ~np.isnan(kp[:, 0]))
        if n_valid >= 1:
            valid_people.append(kp)

    if not valid_people:
        return None

    if len(valid_people) == 1:
        return valid_people[0]

    if prev_kp is not None and not np.all(np.isnan(prev_kp)):
        # Select person closest to previous frame (mean distance of shared valid keypoints)
        best_kp = None
        best_dist = float('inf')
        prev_valid = (prev_kp[:, 2] > CONF_THRESHOLD) & ~np.isnan(prev_kp[:, 0])
        for kp in valid_people:
            curr_valid = (kp[:, 2] > CONF_THRESHOLD) & ~np.isnan(kp[:, 0])
            shared = prev_valid & curr_valid
            if shared.sum() == 0:
                continue
            dist = np.mean(np.sqrt(np.sum((kp[shared, :2] - prev_kp[shared, :2])**2, axis=1)))
            if dist < best_dist:
                best_dist = dist
                best_kp = kp
        if best_kp is not None:
            return best_kp

    # Fallback: person with most valid keypoints
    best_kp = max(valid_people, key=lambda kp: np.sum(kp[:, 2] > CONF_THRESHOLD))
    return best_kp


def load_keypoints_series(cam_json_dir):
    '''Load all frames' keypoints from a single camera directory.

    Handles multi-person frames by selecting the person closest to the
    previous frame's keypoints (tracking by proximity).

    Parameters
    ----------
    cam_json_dir : str or Path
        Directory containing per-frame JSON files.

    Returns
    -------
    np.ndarray
        Shape (N_frames, 26, 3) with [x, y, confidence] per keypoint.
    '''
    files = sorted(glob(os.path.join(str(cam_json_dir), '*.json')))
    if not files:
        raise FileNotFoundError(f'No JSON files found in {cam_json_dir}')

    keypoints_series = np.full((len(files), 26, 3), np.nan)
    prev_kp = None

    for i, f in enumerate(tqdm(files, desc=os.path.basename(str(cam_json_dir)))):
        with open(f) as fp:
            data = json.load(fp)
        people = data.get('people', [])
        if people:
            kp = _select_person(people, prev_kp)
            if kp is not None:
                keypoints_series[i] = kp
                prev_kp = kp

    return keypoints_series


def compute_displacements(keypoints_series):
    '''Compute frame-to-frame Euclidean displacement for each keypoint.

    Parameters
    ----------
    keypoints_series : np.ndarray
        Shape (N_frames, 26, 3).

    Returns
    -------
    np.ndarray
        Shape (N_frames-1, 26). NaN where either frame has conf < 0.1.
    '''
    xy = keypoints_series[:, :, :2]
    conf = keypoints_series[:, :, 2]

    diff = np.diff(xy, axis=0)
    displacements = np.sqrt(np.sum(diff**2, axis=2))

    valid_prev = conf[:-1] > CONF_THRESHOLD
    valid_curr = conf[1:] > CONF_THRESHOLD
    displacements[~(valid_prev & valid_curr)] = np.nan

    return displacements


def detect_jitter(displacements, multiplier=DEFAULT_MULTIPLIER):
    '''Detect jitter events where displacement exceeds threshold.

    Parameters
    ----------
    displacements : np.ndarray
        Shape (N_frames-1, 26).
    multiplier : float
        Threshold = median * multiplier.

    Returns
    -------
    jitter_mask : np.ndarray
        Shape (N_frames-1, 26), bool.
    thresholds : np.ndarray
        Shape (26,).
    medians : np.ndarray
        Shape (26,).
    '''
    medians = np.nanmedian(displacements, axis=0)

    thresholds = medians * multiplier
    thresholds[medians == 0] = 10.0

    jitter_mask = displacements > thresholds[np.newaxis, :]

    return jitter_mask, thresholds, medians


def compute_bb_areas(keypoints_series):
    '''Compute bounding box area for each frame.

    Parameters
    ----------
    keypoints_series : np.ndarray
        Shape (N_frames, 26, 3).

    Returns
    -------
    np.ndarray
        Shape (N_frames,). NaN when fewer than 2 valid keypoints.
    '''
    n_frames = keypoints_series.shape[0]
    bb_areas = np.full(n_frames, np.nan)

    for i in range(n_frames):
        kp = keypoints_series[i]
        valid = kp[:, 2] > CONF_THRESHOLD
        if valid.sum() >= 2:
            valid_xy = kp[valid, :2]
            bb_min = valid_xy.min(axis=0)
            bb_max = valid_xy.max(axis=0)
            bb_areas[i] = (bb_max[0] - bb_min[0]) * (bb_max[1] - bb_min[1])

    return bb_areas


def classify_pattern(frame_idx, kp_idx, keypoints_series, bb_areas, median_bb_area,
                     image_size=DEFAULT_IMAGE_SIZE):
    '''Classify jitter cause. Priority: A > C > D > E.

    Parameters
    ----------
    frame_idx : int
        Index in displacements array. Corresponding keypoints frame is frame_idx + 1.
    kp_idx : int
        Keypoint index.
    keypoints_series : np.ndarray
        Shape (N_frames, 26, 3).
    bb_areas : np.ndarray
        Shape (N_frames,).
    median_bb_area : float
    image_size : tuple
        (width, height) in pixels.

    Returns
    -------
    str
        'A', 'C', 'D', or 'E'.
    '''
    kp = keypoints_series[frame_idx + 1]
    w, h = image_size

    # Pattern A: BB touches image edge
    valid = kp[:, 2] > CONF_THRESHOLD
    if valid.sum() >= 2:
        valid_xy = kp[valid, :2]
        bb_min = valid_xy.min(axis=0)
        bb_max = valid_xy.max(axis=0)
        if (bb_min[0] < EDGE_MARGIN or bb_min[1] < EDGE_MARGIN or
            bb_max[0] > w - EDGE_MARGIN or bb_max[1] > h - EDGE_MARGIN):
            return 'A'

    # Pattern C: Small BB (< 50% of median)
    area = bb_areas[frame_idx + 1]
    if not np.isnan(area) and not np.isnan(median_bb_area) and area < median_bb_area * 0.5:
        return 'C'

    # Pattern D: Low confidence
    if kp[kp_idx, 2] < 0.3:
        return 'D'

    return 'E'


def analyze_camera(cam_json_dir, multiplier=DEFAULT_MULTIPLIER, image_size=DEFAULT_IMAGE_SIZE):
    '''Run full jitter analysis for a single camera.

    Parameters
    ----------
    cam_json_dir : str or Path
    multiplier : float
    image_size : tuple

    Returns
    -------
    dict
        Analysis results for this camera.
    '''
    keypoints_series = load_keypoints_series(cam_json_dir)
    n_frames = keypoints_series.shape[0]

    # Pass 1: Compute statistics
    displacements = compute_displacements(keypoints_series)
    bb_areas = compute_bb_areas(keypoints_series)
    median_bb_area = np.nanmedian(bb_areas)

    # Pass 2: Detect and classify jitter
    jitter_mask, thresholds, medians = detect_jitter(displacements, multiplier)

    events = []
    jitter_indices = np.argwhere(jitter_mask)
    for frame_idx, kp_idx in jitter_indices:
        pattern = classify_pattern(frame_idx, kp_idx, keypoints_series, bb_areas,
                                   median_bb_area, image_size)
        conf = keypoints_series[frame_idx + 1, kp_idx, 2]
        disp = displacements[frame_idx, kp_idx]
        events.append({
            'frame': int(frame_idx + 1),
            'keypoint': HALPE_26_NAMES[kp_idx],
            'keypoint_idx': int(kp_idx),
            'displacement': float(disp),
            'confidence': float(conf),
            'threshold': float(thresholds[kp_idx]),
            'median_displacement': float(medians[kp_idx]),
            'pattern': pattern,
        })

    return {
        'n_frames': n_frames,
        'events': events,
        'jitter_mask': jitter_mask,
        'displacements': displacements,
        'thresholds': thresholds,
        'medians': medians,
        'keypoints_series': keypoints_series,
    }


def save_csv(all_events, output_dir):
    '''Save jitter events to CSV.

    Parameters
    ----------
    all_events : list of (camera_name, event_dict)
    output_dir : Path
    '''
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / 'jitter_events.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['camera', 'frame', 'keypoint', 'keypoint_idx',
                         'displacement', 'confidence', 'threshold',
                         'median_displacement', 'pattern'])
        for cam_name, event in all_events:
            writer.writerow([
                cam_name, event['frame'], event['keypoint'], event['keypoint_idx'],
                f'{event["displacement"]:.1f}', f'{event["confidence"]:.3f}',
                f'{event["threshold"]:.1f}', f'{event["median_displacement"]:.1f}',
                event['pattern'],
            ])
    print(f'CSV saved: {csv_path}')


def save_plots(cam_results, output_dir):
    '''Generate and save analysis plots.

    Parameters
    ----------
    cam_results : dict
        {camera_name: analysis_result}
    output_dir : Path
    '''
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cameras = sorted(cam_results.keys())
    n_kp = len(HALPE_26_NAMES)

    # Plot 1: Jitter frequency heatmap (camera x keypoint)
    jitter_counts = np.zeros((len(cameras), n_kp))
    for i, cam in enumerate(cameras):
        mask = cam_results[cam]['jitter_mask']
        jitter_counts[i] = np.sum(mask, axis=0)

    fig, ax = plt.subplots(figsize=(14, 4))
    im = ax.imshow(jitter_counts, cmap='Reds', aspect='auto')
    ax.set_yticks(range(len(cameras)))
    ax.set_yticklabels(cameras)
    ax.set_xticks(range(n_kp))
    ax.set_xticklabels(HALPE_26_NAMES, rotation=90, fontsize=7)
    ax.set_title('Jitter Frequency: Camera x Keypoint')
    for i in range(len(cameras)):
        for j in range(n_kp):
            val = int(jitter_counts[i, j])
            if val > 0:
                ax.text(j, i, str(val), ha='center', va='center', fontsize=6)
    fig.colorbar(im, ax=ax, shrink=0.8)
    plt.tight_layout()
    path = output_dir / 'jitter_heatmap.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f'Plot saved: {path}')

    # Plot 2: Confidence distribution (jitter vs all)
    all_conf_jitter = []
    all_conf_normal = []
    for cam in cameras:
        kps = cam_results[cam]['keypoints_series']
        mask = cam_results[cam]['jitter_mask']
        conf = kps[1:, :, 2]  # skip first frame (no displacement)
        valid = conf > CONF_THRESHOLD
        all_conf_jitter.extend(conf[mask & valid].tolist())
        all_conf_normal.extend(conf[~mask & valid].tolist())

    fig, ax = plt.subplots(figsize=(8, 5))
    bins = np.arange(0, 1.05, 0.05)
    if all_conf_jitter:
        ax.hist(all_conf_jitter, bins=bins, alpha=0.7, label=f'Jitter (n={len(all_conf_jitter)})',
                density=True, color='red')
    if all_conf_normal:
        ax.hist(all_conf_normal, bins=bins, alpha=0.5, label=f'Normal (n={len(all_conf_normal)})',
                density=True, color='blue')
    ax.set_xlabel('Confidence')
    ax.set_ylabel('Density')
    ax.set_title('Confidence Distribution: Jitter vs Normal')
    ax.legend()
    plt.tight_layout()
    path = output_dir / 'jitter_confidence_dist.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f'Plot saved: {path}')

    # Plot 3: Pattern distribution (stacked bar per camera)
    pattern_labels = ['A', 'C', 'D', 'E']
    pattern_counts = {cam: {p: 0 for p in pattern_labels} for cam in cameras}
    for cam in cameras:
        for event in cam_results[cam]['events']:
            pattern_counts[cam][event['pattern']] += 1

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(cameras))
    bottoms = np.zeros(len(cameras))
    colors = {'A': '#e74c3c', 'C': '#f39c12', 'D': '#3498db', 'E': '#95a5a6'}
    pattern_descriptions = {'A': 'Out-of-frame', 'C': 'Small BB', 'D': 'Low conf', 'E': 'Other'}
    for p in pattern_labels:
        vals = [pattern_counts[cam][p] for cam in cameras]
        ax.bar(x, vals, bottom=bottoms, label=f'{p}: {pattern_descriptions[p]}', color=colors[p])
        bottoms += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(cameras)
    ax.set_ylabel('Jitter Events')
    ax.set_title('Jitter Pattern Distribution per Camera')
    ax.legend()
    plt.tight_layout()
    path = output_dir / 'jitter_pattern_dist.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f'Plot saved: {path}')

    # Plot 4: Displacement timeseries for top 3 jittery keypoints
    total_jitter_per_kp = np.zeros(n_kp)
    for cam in cameras:
        total_jitter_per_kp += np.sum(cam_results[cam]['jitter_mask'], axis=0)
    top3_kp = np.argsort(total_jitter_per_kp)[-3:][::-1]

    fig, axes = plt.subplots(len(top3_kp), 1, figsize=(14, 3 * len(top3_kp)), sharex=True)
    if len(top3_kp) == 1:
        axes = [axes]
    for ax_i, kp_idx in enumerate(top3_kp):
        for cam in cameras:
            disp = cam_results[cam]['displacements'][:, kp_idx]
            threshold = cam_results[cam]['thresholds'][kp_idx]
            frames = np.arange(1, len(disp) + 1)
            axes[ax_i].plot(frames, disp, alpha=0.6, label=cam, linewidth=0.5)
            axes[ax_i].axhline(y=threshold, color='red', linestyle='--', alpha=0.3)
        axes[ax_i].set_ylabel('Displacement (px)')
        axes[ax_i].set_title(f'{HALPE_26_NAMES[kp_idx]} (total jitter: {int(total_jitter_per_kp[kp_idx])})')
        axes[ax_i].legend(fontsize=7)
    axes[-1].set_xlabel('Frame')
    plt.tight_layout()
    path = output_dir / 'jitter_timeseries_top3.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f'Plot saved: {path}')


def format_report(cam_results, multiplier):
    '''Format analysis summary as console report.

    Parameters
    ----------
    cam_results : dict
        {camera_name: analysis_result}
    multiplier : float

    Returns
    -------
    str
    '''
    cameras = sorted(cam_results.keys())
    n_kp = len(HALPE_26_NAMES)

    lines = []
    lines.append('=== 2D Keypoint Jitter Analysis ===')
    lines.append(f'Cameras: {len(cameras)} ({", ".join(cameras)})')
    total_frames = sum(cam_results[c]['n_frames'] for c in cameras)
    lines.append(f'Total frames: {total_frames}')
    lines.append(f'Jitter threshold multiplier: {multiplier}')
    lines.append('')

    # Per-camera jitter count table
    lines.append('--- Jitter Count per Camera x Keypoint ---')
    header = f'{"Keypoint":<14}' + ''.join(f'{c:>8}' for c in cameras) + f'{"total":>8}'
    lines.append(header)
    lines.append('-' * len(header))

    kp_totals = []
    for kp_idx in range(n_kp):
        cam_counts = []
        for cam in cameras:
            cam_counts.append(int(np.sum(cam_results[cam]['jitter_mask'][:, kp_idx])))
        total = sum(cam_counts)
        kp_totals.append((kp_idx, total))
        row = f'{HALPE_26_NAMES[kp_idx]:<14}'
        for c in cam_counts:
            row += f'{c:>8}'
        row += f'{total:>8}'
        lines.append(row)

    total_events = sum(t for _, t in kp_totals)
    row = f'{"TOTAL":<14}'
    for cam in cameras:
        row += f'{len(cam_results[cam]["events"]):>8}'
    row += f'{total_events:>8}'
    lines.append(row)
    lines.append('')

    # Pattern distribution
    lines.append('--- Pattern Distribution ---')
    pattern_labels = ['A', 'C', 'D', 'E']
    pattern_descriptions = {'A': 'Out-of-frame', 'C': 'Small BB', 'D': 'Low confidence', 'E': 'Other'}
    pattern_total = {p: 0 for p in pattern_labels}
    for cam in cameras:
        for event in cam_results[cam]['events']:
            pattern_total[event['pattern']] += 1
    for p in pattern_labels:
        count = pattern_total[p]
        rate = count / total_events * 100 if total_events > 0 else 0
        lines.append(f'  {p} ({pattern_descriptions[p]}): {count} ({rate:.1f}%)')
    lines.append(f'  Total: {total_events}')
    lines.append('')

    # Top 5 most problematic keypoints
    kp_totals_sorted = sorted(kp_totals, key=lambda x: -x[1])
    lines.append('--- Top 5 Problematic Keypoints ---')
    for kp_idx, total in kp_totals_sorted[:5]:
        per_cam = '  '.join(f'{cam}={int(np.sum(cam_results[cam]["jitter_mask"][:, kp_idx]))}'
                            for cam in cameras)
        lines.append(f'  {HALPE_26_NAMES[kp_idx]:<14} total={total}  ({per_cam})')
    lines.append('')

    # Median displacement and thresholds
    lines.append('--- Median Displacement & Threshold (px) ---')
    header2 = f'{"Keypoint":<14}' + ''.join(f'{c+"-med":>10}{c+"-thr":>10}' for c in cameras)
    lines.append(header2)
    lines.append('-' * len(header2))
    for kp_idx in range(n_kp):
        row = f'{HALPE_26_NAMES[kp_idx]:<14}'
        for cam in cameras:
            med = cam_results[cam]['medians'][kp_idx]
            thr = cam_results[cam]['thresholds'][kp_idx]
            row += f'{med:>10.1f}{thr:>10.1f}'
        lines.append(row)
    lines.append('')

    return '\n'.join(lines)


def save_report_md(cam_results, multiplier, output_dir):
    '''Save phase1_results.md with analysis findings.

    Parameters
    ----------
    cam_results : dict
    multiplier : float
    output_dir : Path
    '''
    output_dir = Path(output_dir)
    report = format_report(cam_results, multiplier)

    # Save as phase1_results.md in the parent directory of test_results
    parent_dir = output_dir.parent if output_dir.name == 'test_results' else output_dir
    md_path = parent_dir / 'phase1_results.md'

    cameras = sorted(cam_results.keys())
    n_kp = len(HALPE_26_NAMES)
    total_events = sum(len(cam_results[c]['events']) for c in cameras)

    lines = []
    lines.append('# 012 Phase 1 分析結果: 2Dキーポイント暴れ分析')
    lines.append('')
    lines.append('## 1. データ概要')
    lines.append('')
    for cam in cameras:
        lines.append(f'- {cam}: {cam_results[cam]["n_frames"]} frames')
    lines.append(f'- キーポイント数: {n_kp} (HALPE_26)')
    lines.append(f'- 暴れ閾値倍率: {multiplier}')
    lines.append('')
    lines.append('## 2. 分析結果サマリ')
    lines.append('')
    lines.append(f'暴れ検出イベント合計: **{total_events}**')
    lines.append('')
    lines.append('```')
    lines.append(report)
    lines.append('```')
    lines.append('')
    lines.append('## 3. プロット画像')
    lines.append('')
    lines.append('- `test_results/jitter_heatmap.png`: カメラ×キーポイント暴れ頻度ヒートマップ')
    lines.append('- `test_results/jitter_confidence_dist.png`: 暴れ時 vs 通常時のconfidence分布')
    lines.append('- `test_results/jitter_pattern_dist.png`: 原因パターン別分布')
    lines.append('- `test_results/jitter_timeseries_top3.png`: 暴れ上位3キーポイントの移動量時系列')
    lines.append('')
    lines.append('## 4. 考察')
    lines.append('')
    lines.append('（テスト実行後に記入）')
    lines.append('')

    with open(md_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f'Report saved: {md_path}')


def analyze_jitter(pose_dir, output=None, multiplier=DEFAULT_MULTIPLIER,
                   no_plot=False, image_size=DEFAULT_IMAGE_SIZE):
    '''Main orchestrator for jitter analysis.

    Parameters
    ----------
    pose_dir : str or Path
    output : str or Path or None
    multiplier : float
    no_plot : bool
    image_size : tuple
    '''
    pose_dir = Path(pose_dir)
    if output is None:
        output_dir = Path('docs/012_2d_keypoint_jitter/test_results')
    else:
        output_dir = Path(output)

    cam_dirs = sorted(pose_dir.glob('cam*_json'))
    if not cam_dirs:
        # Try *_json pattern for non-standard directory names
        cam_dirs = sorted(pose_dir.glob('*_json'))
    if not cam_dirs:
        # Check if pose_dir itself contains JSON files
        if list(pose_dir.glob('*.json')):
            cam_dirs = [pose_dir]
    if not cam_dirs:
        raise FileNotFoundError(f'No JSON directories found in {pose_dir}')

    print(f'Loading pose data from {pose_dir} ...')
    cam_results = {}
    all_events = []
    for cam_dir in cam_dirs:
        cam_name = cam_dir.name.replace('_json', '') if cam_dir.name.endswith('_json') else cam_dir.name
        print(f'\nAnalyzing {cam_name} ...')
        result = analyze_camera(cam_dir, multiplier, image_size)
        cam_results[cam_name] = result
        for event in result['events']:
            all_events.append((cam_name, event))
        print(f'  {cam_name}: {result["n_frames"]} frames, {len(result["events"])} jitter events')

    # Console report
    report = format_report(cam_results, multiplier)
    print('\n' + report)

    # Save outputs
    save_csv(all_events, output_dir)
    if not no_plot:
        save_plots(cam_results, output_dir)
    save_report_md(cam_results, multiplier, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze 2D keypoint jitter (frame-to-frame displacement anomalies). '
                    'Detects and classifies jitter events by cause pattern.')
    parser.add_argument('-p', '--pose-dir', required=True,
                        help='Pose directory containing *_json subdirectories, or a directory with JSON files directly.')
    parser.add_argument('-o', '--output', default=None,
                        help='Output directory. Default: docs/012_2d_keypoint_jitter/test_results/')
    parser.add_argument('--multiplier', type=float, default=DEFAULT_MULTIPLIER,
                        help=f'Jitter threshold multiplier (default: {DEFAULT_MULTIPLIER}).')
    parser.add_argument('--no-plot', action='store_true',
                        help='Skip plot image generation.')
    parser.add_argument('--image-width', type=int, default=DEFAULT_IMAGE_SIZE[0],
                        help=f'Image width in pixels (default: {DEFAULT_IMAGE_SIZE[0]}).')
    parser.add_argument('--image-height', type=int, default=DEFAULT_IMAGE_SIZE[1],
                        help=f'Image height in pixels (default: {DEFAULT_IMAGE_SIZE[1]}).')

    args = parser.parse_args()
    analyze_jitter(
        pose_dir=args.pose_dir,
        output=args.output,
        multiplier=args.multiplier,
        no_plot=args.no_plot,
        image_size=(args.image_width, args.image_height),
    )


if __name__ == '__main__':
    main()
