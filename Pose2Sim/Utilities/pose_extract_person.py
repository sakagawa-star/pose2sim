#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## PRIMARY PERSON EXTRACTION                    ##
    ##################################################

    Extract the primary person (patient) from multi-person OpenPose JSON files.
    Uses frame-to-frame keypoint proximity tracking to maintain identity across frames.

    Usage:
        pose_extract_person -i /path/to/json_dir
        pose_extract_person -i /path/to/json_dir -o /path/to/output_dir
'''


## INIT
import os
import sys
import json
import time
import argparse
import numpy as np
from glob import glob
from tqdm import tqdm


## CONSTANTS

CONF_THRESHOLD = 0.1


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
    np.ndarray or None
        Shape (26, 3) keypoints of the selected person, or None if no valid person.
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
        prev_valid = (prev_kp[:, 2] > CONF_THRESHOLD) & ~np.isnan(prev_kp[:, 0])
        best_kp, best_dist = None, float('inf')
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

    return max(valid_people, key=lambda kp: np.sum(kp[:, 2] > CONF_THRESHOLD))


def process(input_dir, output_dir):
    '''Process all JSON files: extract primary person and write to output.

    Parameters
    ----------
    input_dir : str
        Input directory containing per-frame JSON files.
    output_dir : str
        Output directory for extracted JSON files.
    '''
    files = sorted(glob(os.path.join(input_dir, '*.json')))
    if not files:
        raise FileNotFoundError(f'No JSON files found in {input_dir}')

    n_frames = len(files)
    n_empty = 0
    n_multi = 0
    prev_kp = None
    t_start = time.time()

    for f in tqdm(files, desc='Extracting'):
        out_path = os.path.join(output_dir, os.path.basename(f))

        try:
            with open(f) as fp:
                data = json.load(fp)
        except json.JSONDecodeError:
            print(f'Warning: JSON parse error, skipping: {f}', file=sys.stderr)
            with open(out_path, 'w') as fp:
                json.dump({'people': []}, fp)
            n_empty += 1
            continue

        people = data.get('people', [])
        selected = _select_person(people, prev_kp)

        if selected is None:
            out_data = {'people': []}
            n_empty += 1
        else:
            # Count multi-person before selection
            valid_count = 0
            for person in people:
                kps = person.get('pose_keypoints_2d', [])
                if len(kps) >= 26 * 3:
                    kp = np.array(kps).reshape(26, 3)
                    if np.sum((kp[:, 2] > CONF_THRESHOLD) & ~np.isnan(kp[:, 0])) >= 1:
                        valid_count += 1
            if valid_count >= 2:
                n_multi += 1

            out_data = {'people': [{'pose_keypoints_2d': selected.flatten().tolist()}]}
            prev_kp = selected

        with open(out_path, 'w') as fp:
            json.dump(out_data, fp)

    elapsed = time.time() - t_start
    print(f'Done. {n_frames} frames processed in {elapsed:.1f}s.')
    print(f'  Empty: {n_empty} ({n_empty/n_frames*100:.1f}%)')
    print(f'  Multi-person: {n_multi} ({n_multi/n_frames*100:.1f}%)')


def main():
    '''CLI entry point.'''
    parser = argparse.ArgumentParser(
        description='Extract the primary person from multi-person OpenPose JSON files.')
    parser.add_argument('-i', '--input', required=True,
                        help='Input JSON directory')
    parser.add_argument('-o', '--output', default=None,
                        help='Output JSON directory (default: {input}_person)')
    args = parser.parse_args()

    input_dir = args.input
    if not os.path.isdir(input_dir):
        print(f'Error: Input directory not found: {input_dir}', file=sys.stderr)
        sys.exit(1)

    if args.output is None:
        output_dir = input_dir.rstrip('/') + '_person'
    else:
        output_dir = args.output

    os.makedirs(output_dir, exist_ok=True)

    process(input_dir, output_dir)


if __name__ == '__main__':
    main()
