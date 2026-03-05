#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
    ##################################################
    ## ID SWITCH ANALYSIS                           ##
    ##################################################

    Analyze tracking ID switches in 2D pose estimation outputs.
    Quantifies detection count changes and frame-to-frame person matching
    using keypoint distance-based Hungarian matching.

    Usage:
        id_switch_analyze -p /path/to/pose_dir
        id_switch_analyze -p /path/to/pose_dir -o /path/to/output --fps 30
'''


## INIT
import os
import json
import argparse
import csv
import numpy as np
from pathlib import Path
from scipy.optimize import linear_sum_assignment
from tqdm import tqdm


## CONSTANTS

HALPE_26_NAMES = [
    'Nose', 'LEye', 'REye', 'LEar', 'REar',
    'LShoulder', 'RShoulder', 'LElbow', 'RElbow', 'LWrist', 'RWrist',
    'LHip', 'RHip', 'LKnee', 'RKnee', 'LAnkle', 'RAnkle',
    'Head', 'Neck', 'Hip',
    'LBigToe', 'RBigToe', 'LSmallToe', 'RSmallToe', 'LHeel', 'RHeel'
]

CONF_THRESHOLD = 0.1  # Minimum confidence for a keypoint to be considered valid
MIN_VALID_KP = 3      # Minimum valid keypoints for matching


## FUNCTIONS

def parse_frame_people(data):
    '''Extract valid people from a single frame's JSON data.

    Filters out NaN-filled empty entries. A person is valid if they have
    at least one keypoint with conf > 0 and non-NaN coordinates.

    Parameters
    ----------
    data : dict
        Parsed JSON data with 'people' key.

    Returns
    -------
    list of np.ndarray
        Each array has shape (26, 3) with [x, y, conf] per keypoint.
    list
        person_id values for each valid person.
    '''
    people = []
    person_ids = []
    for person in data.get('people', []):
        kp = np.array(person['pose_keypoints_2d']).reshape(26, 3)
        # Filter NaN-filled empty entries
        if np.all(np.isnan(kp[:, 2])) or not np.any(kp[:, 2] > 0):
            continue
        people.append(kp)
        person_ids.append(person.get('person_id', [-1]))
    return people, person_ids


def compute_match_cost(prev_kp, curr_kp):
    '''Compute mean keypoint distance between two people.

    Parameters
    ----------
    prev_kp : np.ndarray
        Shape (26, 3) keypoints of previous frame person.
    curr_kp : np.ndarray
        Shape (26, 3) keypoints of current frame person.

    Returns
    -------
    float
        Mean Euclidean distance of valid shared keypoints, or 1e9 if
        fewer than MIN_VALID_KP shared valid keypoints.
    '''
    valid = (prev_kp[:, 2] > CONF_THRESHOLD) & (curr_kp[:, 2] > CONF_THRESHOLD)
    if valid.sum() < MIN_VALID_KP:
        return 1e9
    dists = np.sqrt(((prev_kp[valid, :2] - curr_kp[valid, :2]) ** 2).sum(axis=1))
    return float(dists.mean())


def match_people(prev_people, curr_people):
    '''Match people between consecutive frames using Hungarian algorithm.

    Parameters
    ----------
    prev_people : list of np.ndarray
        People from previous frame.
    curr_people : list of np.ndarray
        People from current frame.

    Returns
    -------
    list of tuple
        (prev_idx, curr_idx, distance) for matched pairs.
    list of int
        Indices of unmatched previous people (lost).
    list of int
        Indices of unmatched current people (appeared).
    '''
    n_prev = len(prev_people)
    n_curr = len(curr_people)

    if n_prev == 0 or n_curr == 0:
        return [], list(range(n_prev)), list(range(n_curr))

    cost_matrix = np.zeros((n_prev, n_curr))
    for i, prev in enumerate(prev_people):
        for j, curr in enumerate(curr_people):
            cost_matrix[i, j] = compute_match_cost(prev, curr)

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    matches = []
    matched_prev = set()
    matched_curr = set()
    for r, c in zip(row_ind, col_ind):
        dist = cost_matrix[r, c]
        if dist < 1e9:  # Only count as match if valid
            matches.append((r, c, dist))
            matched_prev.add(r)
            matched_curr.add(c)

    unmatched_prev = [i for i in range(n_prev) if i not in matched_prev]
    unmatched_curr = [j for j in range(n_curr) if j not in matched_curr]

    return matches, unmatched_prev, unmatched_curr


def analyze_camera(cam_dir, fps=30):
    '''Analyze ID switches for a single camera.

    Parameters
    ----------
    cam_dir : Path
        Directory containing per-frame JSON files.
    fps : int
        Frame rate for gap duration calculation.

    Returns
    -------
    dict
        Analysis results with keys: 'events', 'match_distances',
        'detection_counts', 'person_id_values', 'n_frames', 'n_errors'.
    '''
    json_files = sorted(cam_dir.glob('*.json'))
    if not json_files:
        raise FileNotFoundError(f'No JSON files found in {cam_dir}')

    events = []
    match_distances = []
    detection_counts = {0: 0, 1: 0, 2: 0, '3+': 0}
    person_id_values = {}
    n_errors = 0

    prev_people = None
    prev_frame_idx = None
    zero_count = 0

    cam_name = cam_dir.name.replace('_json', '')

    for frame_idx, jf in enumerate(tqdm(json_files, desc=f'  {cam_name}', leave=False)):
        # Parse JSON
        try:
            with open(jf) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f'WARNING: {cam_name} frame {frame_idx}: JSON parse error: {e}')
            n_errors += 1
            continue

        current_people, current_ids = parse_frame_people(data)
        curr_count = len(current_people)

        # Record detection count
        if curr_count >= 3:
            detection_counts['3+'] += 1
        else:
            detection_counts[curr_count] += 1

        # Record person_id values
        for pid in current_ids:
            pid_str = str(pid)
            person_id_values[pid_str] = person_id_values.get(pid_str, 0) + 1

        # Handle zero detections
        if curr_count == 0:
            if zero_count == 0 and prev_people is not None:
                events.append({
                    'frame': frame_idx,
                    'event_type': 'no_detection',
                    'prev_count': len(prev_people) if prev_people is not None else 0,
                    'curr_count': 0,
                    'match_distance': '',
                    'gap_frames': '',
                    'pattern': '',
                })
            zero_count += 1
            # Don't update prev_people - keep last valid data
            continue

        # Detection resumed after gap
        if zero_count > 0:
            events.append({
                'frame': frame_idx,
                'event_type': 'detection_resumed',
                'prev_count': 0,
                'curr_count': curr_count,
                'match_distance': '',
                'gap_frames': zero_count,
                'pattern': '',
            })
            zero_count = 0

        # First frame or after error
        if prev_people is None:
            prev_people = current_people
            prev_frame_idx = frame_idx
            continue

        prev_count = len(prev_people)

        # Detection count change
        if prev_count != curr_count:
            events.append({
                'frame': frame_idx,
                'event_type': 'count_change',
                'prev_count': prev_count,
                'curr_count': curr_count,
                'match_distance': '',
                'gap_frames': '',
                'pattern': '',
            })

        # Frame-to-frame matching
        matches, unmatched_prev, unmatched_curr = match_people(prev_people, current_people)

        for _, _, dist in matches:
            match_distances.append(dist)

        for idx in unmatched_prev:
            events.append({
                'frame': frame_idx,
                'event_type': 'person_lost',
                'prev_count': prev_count,
                'curr_count': curr_count,
                'match_distance': '',
                'gap_frames': '',
                'pattern': '',
            })

        for idx in unmatched_curr:
            events.append({
                'frame': frame_idx,
                'event_type': 'person_appeared',
                'prev_count': prev_count,
                'curr_count': curr_count,
                'match_distance': '',
                'gap_frames': '',
                'pattern': '',
            })

        prev_people = current_people
        prev_frame_idx = frame_idx

    return {
        'events': events,
        'match_distances': match_distances,
        'detection_counts': detection_counts,
        'person_id_values': person_id_values,
        'n_frames': len(json_files),
        'n_errors': n_errors,
    }


def classify_patterns(events, fps=30):
    '''Classify events into patterns (A/B/C/D).

    Parameters
    ----------
    events : list of dict
        Event log from analyze_camera.
    fps : int
        Frame rate for gap threshold calculation.

    Returns
    -------
    list of dict
        Events with 'pattern' field populated.
    dict
        Pattern counts.
    '''
    n_gap = fps  # 1 second worth of frames

    # Index events by frame for fast lookup
    frame_events = {}
    for e in events:
        frame = e['frame']
        if frame not in frame_events:
            frame_events[frame] = []
        frame_events[frame].append(e)

    pattern_counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}

    # Pattern A: temporary disappearance -> reappearance within N_gap frames
    # Look for no_detection followed by detection_resumed
    for i, e in enumerate(events):
        if e['event_type'] == 'detection_resumed':
            gap = e.get('gap_frames', 0)
            if isinstance(gap, int) and gap <= n_gap:
                e['pattern'] = 'A'
                pattern_counts['A'] += 1
                # Also mark the corresponding no_detection
                for j in range(i - 1, -1, -1):
                    if events[j]['event_type'] == 'no_detection' and events[j]['pattern'] == '':
                        events[j]['pattern'] = 'A'
                        break

    # Pattern C: count increase followed by decrease (or vice versa) within 10 frames
    count_changes = [(i, e) for i, e in enumerate(events) if e['event_type'] == 'count_change']
    for idx in range(len(count_changes) - 1):
        i1, e1 = count_changes[idx]
        i2, e2 = count_changes[idx + 1]
        if abs(e2['frame'] - e1['frame']) <= 10:
            inc1 = e1['curr_count'] - e1['prev_count']
            inc2 = e2['curr_count'] - e2['prev_count']
            if inc1 * inc2 < 0:  # opposite directions
                if e1['pattern'] == '':
                    e1['pattern'] = 'C'
                    pattern_counts['C'] += 1
                if e2['pattern'] == '':
                    e2['pattern'] = 'C'
                    pattern_counts['C'] += 1

    # Remaining unclassified events: Pattern D
    for e in events:
        if e['pattern'] == '' and e['event_type'] in ('count_change', 'person_lost',
                                                        'person_appeared', 'no_detection',
                                                        'detection_resumed'):
            e['pattern'] = 'D'
            pattern_counts['D'] += 1

    return events, pattern_counts


def compute_distance_stats(match_distances):
    '''Compute statistics on matching distances.

    Parameters
    ----------
    match_distances : list of float

    Returns
    -------
    dict
        Statistics with keys: mean, median, p95, p99, min, max, count.
    '''
    if not match_distances:
        return {k: 0.0 for k in ['mean', 'median', 'p95', 'p99', 'min', 'max', 'count']}

    arr = np.array(match_distances)
    return {
        'mean': float(np.mean(arr)),
        'median': float(np.median(arr)),
        'p95': float(np.percentile(arr, 95)),
        'p99': float(np.percentile(arr, 99)),
        'min': float(np.min(arr)),
        'max': float(np.max(arr)),
        'count': len(arr),
    }


def format_report(cam_results, fps):
    '''Format analysis results as a Markdown report string.

    Parameters
    ----------
    cam_results : dict
        {camera_name: analysis_result}
    fps : int

    Returns
    -------
    str
        Markdown-formatted report.
    '''
    lines = []
    lines.append('# 011 IDスイッチ分析結果（Phase 1）')
    lines.append('')
    lines.append('## 1. データ概要')
    lines.append('')
    lines.append(f'- フレームレート: {fps} fps')
    lines.append(f'- カメラ数: {len(cam_results)}')
    for cam, res in sorted(cam_results.items()):
        lines.append(f'- {cam}: {res["n_frames"]} フレーム'
                     f' (エラー: {res["n_errors"]})')
    lines.append('')

    # Detection count distribution
    lines.append('## 2. 検出人数の分布')
    lines.append('')
    lines.append('| カメラ | 0人 | 1人 | 2人 | 3人+ |')
    lines.append('|--------|-----|-----|-----|------|')
    for cam, res in sorted(cam_results.items()):
        dc = res['detection_counts']
        total = res['n_frames'] - res['n_errors']
        lines.append(f'| {cam} | {dc[0]} ({dc[0]/total*100:.1f}%) '
                     f'| {dc[1]} ({dc[1]/total*100:.1f}%) '
                     f'| {dc[2]} ({dc[2]/total*100:.1f}%) '
                     f'| {dc["3+"]} ({dc["3+"]/total*100:.1f}%) |')
    lines.append('')

    # person_id values
    lines.append('## 3. person_idの分布')
    lines.append('')
    for cam, res in sorted(cam_results.items()):
        lines.append(f'- {cam}: {res["person_id_values"]}')
    lines.append('')

    # Matching distance statistics
    lines.append('## 4. フレーム間マッチング距離の分布')
    lines.append('')
    lines.append('| カメラ | サンプル数 | 平均 | 中央値 | 95%ile | 99%ile | 最小 | 最大 |')
    lines.append('|--------|-----------|------|--------|--------|--------|------|------|')
    for cam, res in sorted(cam_results.items()):
        ds = res['distance_stats']
        lines.append(f'| {cam} | {ds["count"]} | {ds["mean"]:.1f} | {ds["median"]:.1f} '
                     f'| {ds["p95"]:.1f} | {ds["p99"]:.1f} '
                     f'| {ds["min"]:.1f} | {ds["max"]:.1f} |')
    lines.append('')

    # Pattern classification
    lines.append('## 5. イベントパターン分類')
    lines.append('')
    lines.append(f'- パターンA: 一時的消失→再出現（{fps}フレーム={fps/fps:.0f}秒以内）')
    lines.append('- パターンB: 人数変動なし・マッチング距離異常（※Phase 1では未使用: 閾値が未決定のため）')
    lines.append('- パターンC: 段階的な人数変動（10フレーム以内の増減反転）')
    lines.append('- パターンD: その他')
    lines.append('')
    lines.append('| カメラ | A | B | C | D | 合計イベント |')
    lines.append('|--------|---|---|---|---|------------|')
    for cam, res in sorted(cam_results.items()):
        pc = res['pattern_counts']
        total = sum(pc.values())
        lines.append(f'| {cam} | {pc["A"]} | {pc["B"]} | {pc["C"]} | {pc["D"]} | {total} |')
    lines.append('')

    # Event type breakdown
    lines.append('## 6. イベントタイプ別集計')
    lines.append('')
    for cam, res in sorted(cam_results.items()):
        event_types = {}
        for e in res['events']:
            et = e['event_type']
            event_types[et] = event_types.get(et, 0) + 1
        lines.append(f'### {cam}')
        for et, count in sorted(event_types.items()):
            lines.append(f'- {et}: {count}')
        lines.append('')

    # Matching failure rate
    lines.append('## 7. マッチング失敗率')
    lines.append('')
    lines.append('マッチング失敗 = person_lost + person_appeared イベント（人物の出現・消失）')
    lines.append('')
    for cam, res in sorted(cam_results.items()):
        n_lost = sum(1 for e in res['events'] if e['event_type'] == 'person_lost')
        n_appeared = sum(1 for e in res['events'] if e['event_type'] == 'person_appeared')
        total_frames = res['n_frames'] - res['n_errors']
        lines.append(f'- {cam}: 消失={n_lost} ({n_lost/total_frames*100:.2f}%), '
                     f'出現={n_appeared} ({n_appeared/total_frames*100:.2f}%)')
    lines.append('')

    return '\n'.join(lines)


def save_events_csv(cam_results, output_dir):
    '''Save all events to a CSV file.

    Parameters
    ----------
    cam_results : dict
        {camera_name: analysis_result}
    output_dir : Path
    '''
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / 'id_switch_events.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['camera', 'frame', 'event_type', 'prev_person_count',
                         'curr_person_count', 'match_distance', 'gap_frames', 'pattern'])
        for cam in sorted(cam_results.keys()):
            for e in cam_results[cam]['events']:
                writer.writerow([
                    cam,
                    e['frame'],
                    e['event_type'],
                    e['prev_count'],
                    e['curr_count'],
                    e['match_distance'],
                    e['gap_frames'],
                    e['pattern'],
                ])

    print(f'Events CSV saved: {csv_path}')
    return csv_path


def save_distance_csv(cam_results, output_dir):
    '''Save matching distance data to a CSV file.

    Parameters
    ----------
    cam_results : dict
        {camera_name: analysis_result}
    output_dir : Path
    '''
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / 'match_distances.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['camera', 'distance'])
        for cam in sorted(cam_results.keys()):
            for d in cam_results[cam]['match_distances']:
                writer.writerow([cam, f'{d:.2f}'])

    print(f'Distance CSV saved: {csv_path}')
    return csv_path


def analyze_id_switches(pose_dir, output_dir=None, fps=30):
    '''Main orchestrator for ID switch analysis.

    Parameters
    ----------
    pose_dir : str or Path
        Pose directory containing cam*_json subdirectories.
    output_dir : str or Path or None
        Output directory. Default: docs/011_id_switch_analysis/test_results/
    fps : int
        Frame rate.

    Returns
    -------
    dict
        {camera_name: analysis_result}
    '''
    pose_dir = Path(pose_dir)
    if output_dir is None:
        # Default output to project docs directory
        output_dir = Path('docs/011_id_switch_analysis/test_results')
    else:
        output_dir = Path(output_dir)

    cam_dirs = sorted(pose_dir.glob('cam*_json'))
    if not cam_dirs:
        raise FileNotFoundError(f'No cam*_json directories found in {pose_dir}')

    print(f'Analyzing ID switches in {pose_dir}')
    print(f'Found {len(cam_dirs)} cameras: {[d.name for d in cam_dirs]}')
    print(f'FPS: {fps}')
    print()

    cam_results = {}
    for cam_dir in cam_dirs:
        cam_name = cam_dir.name.replace('_json', '')
        print(f'Processing {cam_name}...')

        result = analyze_camera(cam_dir, fps=fps)

        # Compute distance statistics
        result['distance_stats'] = compute_distance_stats(result['match_distances'])

        # Classify patterns
        result['events'], result['pattern_counts'] = classify_patterns(result['events'], fps=fps)

        cam_results[cam_name] = result

        # Print summary
        ds = result['distance_stats']
        dc = result['detection_counts']
        print(f'  Frames: {result["n_frames"]}, Errors: {result["n_errors"]}')
        print(f'  Detection: 0={dc[0]}, 1={dc[1]}, 2={dc[2]}, 3+={dc["3+"]}')
        print(f'  Match distances: mean={ds["mean"]:.1f}, median={ds["median"]:.1f}, '
              f'p95={ds["p95"]:.1f}, p99={ds["p99"]:.1f}')
        print(f'  Events: {len(result["events"])}')
        print(f'  Patterns: {result["pattern_counts"]}')
        print()

    # Generate report
    report = format_report(cam_results, fps)

    # Save outputs
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir.parent / 'phase1_results.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f'Report saved: {report_path}')

    save_events_csv(cam_results, output_dir)
    save_distance_csv(cam_results, output_dir)

    # Also print report to console
    print()
    print(report)

    return cam_results


def main():
    parser = argparse.ArgumentParser(
        description='Analyze tracking ID switches in 2D pose estimation outputs. '
                    'Quantifies detection count changes and frame-to-frame person matching.')
    parser.add_argument('-p', '--pose-dir', required=True,
                        help='Pose directory path containing cam*_json subdirectories.')
    parser.add_argument('-o', '--output-dir', default=None,
                        help='Output directory path. Default: docs/011_id_switch_analysis/test_results/')
    parser.add_argument('--fps', type=int, default=30,
                        help='Frame rate (default: 30). Used for pattern A gap threshold.')

    args = parser.parse_args()
    analyze_id_switches(
        pose_dir=args.pose_dir,
        output_dir=args.output_dir,
        fps=args.fps,
    )


if __name__ == '__main__':
    main()
