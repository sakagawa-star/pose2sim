#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## KEYPOINT CONFIDENCE TIMELINE                 ##
    ##################################################

    Plot per-frame keypoint confidence scores as a timeline scatter plot.
    Outputs CSV data and PNG plot for visual inspection of confidence patterns.

    Usage:
        confidence_timeline -j /path/to/json_dir
        confidence_timeline -j /path/to/json_dir -k Nose,Neck,RShoulder,LShoulder
        confidence_timeline -j /path/to/json_dir -t 0.3,0.5 -o /path/to/output
'''


## INIT
import os
import sys
import json
import csv
import time
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from glob import glob
from tqdm import tqdm


## CONSTANTS

HALPE_26_INDICES = {
    'Nose': 0, 'LEye': 1, 'REye': 2, 'LEar': 3, 'REar': 4,
    'LShoulder': 5, 'RShoulder': 6, 'LElbow': 7, 'RElbow': 8,
    'LWrist': 9, 'RWrist': 10, 'LHip': 11, 'RHip': 12,
    'LKnee': 13, 'RKnee': 14, 'LAnkle': 15, 'RAnkle': 16,
    'Head': 17, 'Neck': 18, 'Hip': 19,
    'LBigToe': 20, 'RBigToe': 21, 'LSmallToe': 22, 'RSmallToe': 23,
    'LHeel': 24, 'RHeel': 25
}

N_KEYPOINTS = 26

PERSON_COLORS = ['C0', 'C1', 'C2', 'C3', 'C4']  # C0=blue, C1=orange, C2=green, C3=red, C4=purple
DEFAULT_COLOR = 'gray'  # Person 5以降


## FUNCTIONS

def process(json_dir, keypoint_names, output_dir, thresholds):
    '''Analyze keypoint confidence timeline and output CSV + PNG.

    Parameters
    ----------
    json_dir : str
        Path to directory containing per-frame JSON files.
    keypoint_names : list[str]
        List of keypoint names to analyze.
    output_dir : str
        Path to output directory.
    thresholds : list[float] or None
        Threshold values for horizontal reference lines. None for no lines.
    '''
    # List JSON files
    files = sorted(glob(os.path.join(json_dir, '*.json')))
    if not files:
        raise FileNotFoundError(f'No JSON files found in {json_dir}')

    # Resolve keypoint indices
    target_keypoints = {}
    for name in keypoint_names:
        if name not in HALPE_26_INDICES:
            available = ', '.join(sorted(HALPE_26_INDICES.keys()))
            raise ValueError(f'Unknown keypoint: {name}. Available: {available}')
        target_keypoints[name] = HALPE_26_INDICES[name]

    os.makedirs(output_dir, exist_ok=True)

    n_frames = len(files)
    print(f'JSON files: {n_frames}')
    print(f'Keypoints: {", ".join(keypoint_names)}')
    print(f'Output: {output_dir}')

    # Collect data
    rows = []
    t_start = time.time()

    for frame_idx, f in enumerate(tqdm(files, desc='Reading')):
        try:
            with open(f) as fp:
                data = json.load(fp)
        except json.JSONDecodeError:
            print(f'Warning: JSON parse error, skipping: {f}', file=sys.stderr)
            continue

        for person_idx, person in enumerate(data.get('people', [])):
            kps = person.get('pose_keypoints_2d', [])
            if len(kps) < N_KEYPOINTS * 3:
                continue
            kp = np.array(kps[:N_KEYPOINTS * 3]).reshape(N_KEYPOINTS, 3)
            for name, idx in target_keypoints.items():
                rows.append((frame_idx, person_idx, name, float(kp[idx, 2])))

    # CSV output
    csv_path = os.path.join(output_dir, 'confidence_timeline.csv')
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frame', 'person', 'keypoint', 'confidence'])
        writer.writerows(rows)

    # PNG plot
    png_path = os.path.join(output_dir, 'confidence_timeline.png')
    n_kp = len(keypoint_names)
    fig, axes = plt.subplots(n_kp, 1, figsize=(14, 2.5 * n_kp), sharex=True)
    if n_kp == 1:
        axes = [axes]

    # Pre-group rows by (keypoint, person) for efficiency
    grouped = {}
    for frame_idx, person_idx, kp_name, conf in rows:
        key = (kp_name, person_idx)
        if key not in grouped:
            grouped[key] = ([], [])
        grouped[key][0].append(frame_idx)
        grouped[key][1].append(conf)

    for ax, name in zip(axes, keypoint_names):
        # Plot per person with color coding
        person_indices = sorted(set(pidx for (kn, pidx) in grouped if kn == name))
        for pidx in person_indices:
            key = (name, pidx)
            if key not in grouped:
                continue
            frames, confs = grouped[key]
            color = PERSON_COLORS[pidx] if pidx < len(PERSON_COLORS) else DEFAULT_COLOR
            ax.scatter(frames, confs, s=1, alpha=0.5, color=color, label=f'P{pidx}')
        ax.set_ylabel(name)
        ax.set_ylim(-0.05, 1.05)

        # Threshold lines
        if thresholds:
            for th in thresholds:
                ax.axhline(y=th, color='r', linestyle='--', alpha=0.5, label=f'thr={th}')

        ax.legend(loc='lower right', fontsize=8, markerscale=5)

    axes[-1].set_xlabel('Frame')
    fig.suptitle('Keypoint Confidence Timeline')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(png_path, dpi=150)
    plt.close(fig)

    elapsed = time.time() - t_start
    print(f'Done. {n_frames} frames, {len(rows)} data points in {elapsed:.1f}s.')
    print(f'  CSV: {csv_path}')
    print(f'  PNG: {png_path}')


def main():
    '''CLI entry point.'''
    parser = argparse.ArgumentParser(
        description='Plot keypoint confidence timeline from JSON files.')
    parser.add_argument('-j', '--json_dir', required=True,
                        help='Input JSON directory')
    parser.add_argument('-k', '--keypoints', default='Nose,Neck,RShoulder,LShoulder',
                        help='Keypoint names, comma-separated (default: Nose,Neck,RShoulder,LShoulder)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output directory (default: {json_dir}_conf_timeline)')
    parser.add_argument('-t', '--threshold', default=None,
                        help='Threshold lines, comma-separated (e.g., 0.3,0.5). Default: none')
    args = parser.parse_args()

    json_dir = args.json_dir
    if not os.path.isdir(json_dir):
        print(f'Error: Input directory not found: {json_dir}', file=sys.stderr)
        sys.exit(1)

    keypoint_names = [k.strip() for k in args.keypoints.split(',')]

    if args.output is None:
        output_dir = json_dir.rstrip('/') + '_conf_timeline'
    else:
        output_dir = args.output

    thresholds = None
    if args.threshold:
        try:
            thresholds = [float(t.strip()) for t in args.threshold.split(',')]
        except ValueError:
            print(f'Error: Invalid threshold value: {args.threshold}', file=sys.stderr)
            sys.exit(1)

    process(json_dir, keypoint_names, output_dir, thresholds)


if __name__ == '__main__':
    main()
