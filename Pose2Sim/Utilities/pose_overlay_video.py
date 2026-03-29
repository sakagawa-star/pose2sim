#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## 2D KEYPOINT OVERLAY VIDEO GENERATOR          ##
    ##################################################

    Generate a video with 2D keypoints and skeleton overlaid on a background image
    (or black background) from OpenPose-format JSON files.

    Usage:
        pose_overlay_video -j /path/to/json_dir
        pose_overlay_video -j /path/to/json_dir -b /path/to/background.jpg
        pose_overlay_video -j /path/to/json_dir -b bg.jpg -o output.mp4 --fps 30 --size 1920x1080
'''


## INIT
import os
import sys
import json
import time
import argparse
import numpy as np
import cv2
from glob import glob
from tqdm import tqdm

from Pose2Sim.common import draw_skel, draw_keypts
from Pose2Sim.skeletons import HALPE_26


## CONSTANTS

N_KEYPOINTS = 26


## FUNCTIONS

def process(json_dir, background_path, output_path, fps, size, conf_threshold=0.0):
    '''Generate overlay video from JSON keypoints and background image.

    Parameters
    ----------
    json_dir : str
        Path to directory containing per-frame JSON files.
    background_path : str or None
        Path to background image. None for black background.
    output_path : str
        Path to output MP4 video.
    fps : int
        Frame rate of output video.
    size : tuple[int, int]
        (width, height) of the video. Ignored when background_path is provided.
    conf_threshold : float
        Confidence threshold. Keypoints with confidence < this value are hidden.
    '''
    # List JSON files
    files = sorted(glob(os.path.join(json_dir, '*.json')))
    if not files:
        raise FileNotFoundError(f'No JSON files found in {json_dir}')

    n_frames = len(files)

    # Prepare background image
    if background_path is not None:
        bg = cv2.imread(background_path)
        if bg is None:
            raise FileNotFoundError(f'Cannot read background image: {background_path}')
    else:
        W, H = size
        bg = np.zeros((H, W, 3), dtype=np.uint8)

    H, W = bg.shape[:2]

    print(f'JSON files: {n_frames}')
    print(f'Background: {W}x{H} ({"image" if background_path else "black"})')
    print(f'Output: {output_path}')
    print(f'FPS: {fps}')
    if conf_threshold > 0.0:
        print(f'Confidence threshold: {conf_threshold}')

    # Set up video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (W, H))
    if not out.isOpened():
        raise RuntimeError(f'Failed to create video writer: {output_path}')

    n_empty = 0
    t_start = time.time()

    for frame_idx, f in enumerate(tqdm(files, desc='Rendering')):
        img = bg.copy()

        # Frame number
        cv2.putText(img, f'Frame: {frame_idx}', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

        # Read JSON
        try:
            with open(f) as fp:
                data = json.load(fp)
        except json.JSONDecodeError:
            print(f'Warning: JSON parse error, skipping: {f}', file=sys.stderr)
            n_empty += 1
            out.write(img)
            continue

        # Extract keypoints for all people
        people = data.get('people', [])
        X_list, Y_list, scores_list = [], [], []
        for person in people:
            kps = person.get('pose_keypoints_2d', [])
            if len(kps) < N_KEYPOINTS * 3:
                continue
            kp = np.array(kps[:N_KEYPOINTS * 3]).reshape(N_KEYPOINTS, 3)
            mask = (kp[:, 2] <= 0) | (kp[:, 2] < conf_threshold)
            kp[mask, :2] = np.nan
            X_list.append(kp[:, 0])
            Y_list.append(kp[:, 1])
            scores_list.append(kp[:, 2])

        if not X_list:
            n_empty += 1
            out.write(img)
            continue

        # Draw keypoints and skeleton
        img = draw_keypts(img, X_list, Y_list, scores_list, cmap_str='RdYlGn')
        img = draw_skel(img, X_list, Y_list, HALPE_26)

        out.write(img)

    out.release()

    elapsed = time.time() - t_start
    print(f'Done. {n_frames} frames rendered in {elapsed:.1f}s.')
    print(f'  Empty frames: {n_empty} ({n_empty/n_frames*100:.1f}%)')
    print(f'  Output: {output_path}')


def main():
    '''CLI entry point.'''
    parser = argparse.ArgumentParser(
        description='Generate overlay video from 2D keypoint JSON files.')
    parser.add_argument('-j', '--json_dir', required=True,
                        help='Input JSON directory')
    parser.add_argument('-b', '--background', default=None,
                        help='Background image path (default: black background)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output video path (default: {json_dir}_overlay.mp4)')
    parser.add_argument('-f', '--fps', type=int, default=30,
                        help='Frame rate (default: 30)')
    parser.add_argument('-s', '--size', default='1920x1080',
                        help='Image size WxH (default: 1920x1080). Ignored when -b is specified.')
    parser.add_argument('-c', '--conf_threshold', type=float, default=0.0,
                        help='Confidence threshold (default: 0.0). Keypoints below this value are hidden.')
    args = parser.parse_args()

    json_dir = args.json_dir
    if not os.path.isdir(json_dir):
        print(f'Error: Input directory not found: {json_dir}', file=sys.stderr)
        sys.exit(1)

    if args.output is None:
        output_path = json_dir.rstrip('/') + '_overlay.mp4'
    else:
        output_path = args.output

    # Parse size
    try:
        parts = args.size.split('x')
        if len(parts) != 2:
            raise ValueError
        size = (int(parts[0]), int(parts[1]))
    except ValueError:
        print(f'Error: Invalid size format: {args.size}. Use WxH (e.g., 1920x1080)', file=sys.stderr)
        sys.exit(1)

    process(json_dir, args.background, output_path, args.fps, size, args.conf_threshold)


if __name__ == '__main__':
    main()
