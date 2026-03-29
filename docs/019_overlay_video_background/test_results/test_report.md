# 019: MP4 Background Support - Test Report

Date: 2026-03-29

## Environment

- pip install -e /home/sakagawa/git/pose2sim (pose2sim 0.10.40.dev89)
- Python env: micromamba Pose2Sim
- Test data: `Pose2Sim/20260227-dgtw2-lab2/` (cam01, 1800 frames, 30fps, 1920x1080)

## 1. CLI Help Verification

```
$ pose_overlay_video --help
usage: pose_overlay_video [-h] -j JSON_DIR [-b BACKGROUND] [-o OUTPUT]
                          [-f FPS] [-s SIZE] [-c CONF_THRESHOLD]

Generate overlay video from 2D keypoint JSON files.

options:
  -h, --help            show this help message and exit
  -j JSON_DIR, --json_dir JSON_DIR
                        Input JSON directory
  -b BACKGROUND, --background BACKGROUND
                        Background image or video path (default: black
                        background)
  -o OUTPUT, --output OUTPUT
                        Output video path (default: {json_dir}_overlay.mp4)
  -f FPS, --fps FPS     Frame rate (default: auto from video, or 30)
  -s SIZE, --size SIZE  Image size WxH (default: 1920x1080). Ignored when -b
                        is specified.
  -c CONF_THRESHOLD, --conf_threshold CONF_THRESHOLD
                        Confidence threshold (default: 0.0). Keypoints below
                        this value are hidden.
```

**Result: PASS**
- `-b` description: "Background image or video path" (image or video)
- `--fps` default: "auto from video, or 30" (changed from fixed 30)

## 2. Test Cases

### Test 4a: Video Background

```
$ pose_overlay_video -j .../pose/cam01_json -b .../videos/cam01.mp4 -o /tmp/test_019_video_bg.mp4
JSON files: 1800
Background: 1920x1080 (video: .../videos/cam01.mp4)
Output: /tmp/test_019_video_bg.mp4
FPS: 30
Done. 1800 frames rendered in 12.7s.
  Empty frames: 0 (0.0%)
```

**Result: PASS**
- Video detected as background (type: "video")
- FPS auto-detected: 30 (matches source video's 30.0fps)
- Output: 62,628,382 bytes

### Test 4b: Image Background (backward compatibility)

```
$ pose_overlay_video -j .../pose/cam01_json -b /tmp/test_frame.jpg -o /tmp/test_019_image_bg.mp4
JSON files: 1800
Background: 1920x1080 (image)
Output: /tmp/test_019_image_bg.mp4
FPS: 30
Done. 1800 frames rendered in 10.2s.
  Empty frames: 0 (0.0%)
```

**Result: PASS**
- Image correctly detected (type: "image")
- FPS defaults to 30 (no video to auto-detect from)
- Output: 45,686,056 bytes

### Test 4c: Black Background (backward compatibility)

```
$ pose_overlay_video -j .../pose/cam01_json -o /tmp/test_019_black_bg.mp4 --size 1920x1080
JSON files: 1800
Background: 1920x1080 (black)
Output: /tmp/test_019_black_bg.mp4
FPS: 30
Done. 1800 frames rendered in 9.2s.
  Empty frames: 0 (0.0%)
```

**Result: PASS**
- Black background mode still works
- FPS: 30 (default, no --fps specified)
- Output: 30,247,254 bytes

### Test 4d: Video Background + Confidence Threshold 0.3

```
$ pose_overlay_video -j .../pose/cam01_json -b .../videos/cam01.mp4 -o /tmp/test_019_video_conf03.mp4 -c 0.3
JSON files: 1800
Background: 1920x1080 (video: .../videos/cam01.mp4)
Output: /tmp/test_019_video_conf03.mp4
FPS: 30
Confidence threshold: 0.3
Done. 1800 frames rendered in 12.8s.
  Empty frames: 0 (0.0%)
```

**Result: PASS**
- Video background + confidence threshold works together
- Output: 62,613,153 bytes (slightly smaller than 4a due to fewer drawn keypoints)

## 3. Output File Summary

| Test | File | Size |
|------|------|------|
| 4a Video BG | /tmp/test_019_video_bg.mp4 | 59.7 MB |
| 4b Image BG | /tmp/test_019_image_bg.mp4 | 43.6 MB |
| 4c Black BG | /tmp/test_019_black_bg.mp4 | 28.8 MB |
| 4d Video+conf0.3 | /tmp/test_019_video_conf03.mp4 | 59.7 MB |

## 4. Verification Summary

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `-b` help text mentions "image or video" | Yes | "Background image or video path" | PASS |
| `--fps` default auto from video | Yes | "auto from video, or 30" | PASS |
| Video BG: FPS auto-detected | 30 | 30 | PASS |
| Image BG: backward compatible | Works | Works | PASS |
| Black BG: backward compatible | Works | Works | PASS |
| Black BG: FPS defaults to 30 | 30 | 30 | PASS |
| Video BG + conf threshold | Works | Works | PASS |
| All output files generated | 4 files | 4 files | PASS |

## Conclusion

All 4 test cases passed. The MP4 background support is working correctly:
- Video backgrounds are auto-detected and frames are read per-frame
- FPS is automatically extracted from video backgrounds
- Backward compatibility with image backgrounds and black backgrounds is maintained
- Confidence threshold works correctly with video backgrounds
