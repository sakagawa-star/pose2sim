#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## 2D KEYPOINT OVERLAY VIDEO GENERATOR          ##
    ##################################################

    Generate a video with 2D keypoints and skeleton overlaid on a background image,
    video, or black background from OpenPose-format JSON files.

    Usage:
        pose_overlay_video -j /path/to/json_dir
        pose_overlay_video -j /path/to/json_dir -b /path/to/background.jpg
        pose_overlay_video -j /path/to/json_dir -b /path/to/video.mp4
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
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp'}


## FUNCTIONS

def process(json_dir, background_path, output_path, fps, size, conf_threshold=0.0):
    '''Generate overlay video from JSON keypoints and background image or video.

    Parameters
    ----------
    json_dir : str
        Path to directory containing per-frame JSON files.
    background_path : str or None
        Path to background image or video. None for black background.
    output_path : str
        Path to output MP4 video.
    fps : int or None
        Frame rate of output video. None for auto (from video, or 30).
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

    # Prepare background
    bg = None
    bg_cap = None

    if background_path is not None:
        ext = os.path.splitext(background_path)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            bg_cap = cv2.VideoCapture(background_path)
            if not bg_cap.isOpened():
                raise FileNotFoundError(f'Cannot open background video: {background_path}')
            bg_mode = 'video'
        elif ext in IMAGE_EXTENSIONS:
            bg = cv2.imread(background_path)
            if bg is None:
                raise FileNotFoundError(f'Cannot read background image: {background_path}')
            bg_mode = 'image'
        else:
            bg = cv2.imread(background_path)
            if bg is not None:
                bg_mode = 'image'
            else:
                bg_cap = cv2.VideoCapture(background_path)
                if bg_cap.isOpened():
                    bg_mode = 'video'
                else:
                    raise FileNotFoundError(f'Cannot read background file: {background_path}')
    else:
        bg_mode = 'black'
        W, H = size
        bg = np.zeros((H, W, 3), dtype=np.uint8)

    # Get resolution, FPS, and frame count
    if bg_mode == 'video':
        W = int(bg_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(bg_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps is None:
            video_fps = bg_cap.get(cv2.CAP_PROP_FPS)
            fps = int(round(video_fps)) if video_fps > 0 else 30
    elif bg_mode == 'image':
        H, W = bg.shape[:2]
        if fps is None:
            fps = 30
    else:  # black
        if fps is None:
            fps = 30

    # Determine render frame count
    if bg_mode == 'video':
        n_video_frames = int(bg_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        n_render = min(n_frames, n_video_frames)
        if n_frames != n_video_frames:
            print(f'Warning: JSON files ({n_frames}) and video frames ({n_video_frames}) count mismatch. '
                  f'Rendering {n_render} frames.', file=sys.stderr)
    else:
        n_render = n_frames

    print(f'JSON files: {n_frames}')
    if bg_mode == 'video':
        print(f'Background: {W}x{H} (video: {background_path})')
    else:
        print(f'Background: {W}x{H} ({"image" if bg_mode == "image" else "black"})')
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

    for frame_idx, f in enumerate(tqdm(files[:n_render], desc='Rendering')):
        # Get background frame
        if bg_mode == 'video':
            ret, img = bg_cap.read()
            if not ret:
                break
        else:
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

    if bg_cap is not None:
        bg_cap.release()
    out.release()

    elapsed = time.time() - t_start
    print(f'Done. {n_render} frames rendered in {elapsed:.1f}s.')
    print(f'  Empty frames: {n_empty} ({n_empty/n_render*100:.1f}%)')
    print(f'  Output: {output_path}')


def main():
    '''CLI entry point.'''
    parser = argparse.ArgumentParser(
        description='Generate overlay video from 2D keypoint JSON files.')
    parser.add_argument('-j', '--json_dir', required=True,
                        help='Input JSON directory')
    parser.add_argument('-b', '--background', default=None,
                        help='Background image or video path (default: black background)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output video path (default: {json_dir}_overlay.mp4)')
    parser.add_argument('-f', '--fps', type=int, default=None,
                        help='Frame rate (default: auto from video, or 30)')
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
