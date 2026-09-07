"""Subject/saliency-aware horizontal crop tracking for vertical video."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CropKeyframe:
    time: float
    x: float
    confidence: float


def crop_dimensions(width: int, height: int) -> tuple[int, int]:
    target_width = min(width, round(height * 9 / 16))
    return target_width, height


def smooth_keyframes(
    keyframes: list[CropKeyframe],
    frame_width: int,
    crop_width: int,
    smoothing: float = 0.82,
) -> list[CropKeyframe]:
    if not keyframes:
        return []
    maximum = max(0.0, float(frame_width - crop_width))
    result = [
        CropKeyframe(keyframes[0].time, _clamp(keyframes[0].x, maximum), keyframes[0].confidence)
    ]
    for point in keyframes[1:]:
        raw = _clamp(point.x, maximum)
        prior = result[-1].x
        x = smoothing * prior + (1 - smoothing) * raw
        result.append(CropKeyframe(point.time, round(x, 3), point.confidence))
    return result


def analyze_subject_path(
    source: Path,
    start: float,
    end: float,
    frame_width: int,
    crop_width: int,
    sample_seconds: float = 1.0,
) -> list[CropKeyframe]:
    """Sample faces first, then saliency/motion; return restrained crop-left positions."""
    try:
        import cv2
    except ImportError:
        return [CropKeyframe(0.0, (frame_width - crop_width) / 2, 0.0)]
    capture = cv2.VideoCapture(str(source))
    classifier = getattr(cv2, "CascadeClassifier", None)
    cv2_data = getattr(cv2, "data", None)
    cascade_root = getattr(cv2_data, "haarcascades", "")
    face_detector = (
        classifier(str(Path(cascade_root) / "haarcascade_frontalface_default.xml"))
        if classifier is not None and cascade_root
        else None
    )
    points: list[CropKeyframe] = []
    prior_gray = None
    time = start
    while time <= end:
        capture.set(cv2.CAP_PROP_POS_MSEC, time * 1000)
        ok, frame = capture.read()
        if not ok:
            time += sample_seconds
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = (
            face_detector.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(36, 36))
            if face_detector is not None
            else ()
        )
        confidence = 0.35
        if len(faces):
            weighted = sorted(faces, key=lambda face: face[2] * face[3], reverse=True)[:2]
            focus_x = sum(x + width / 2 for x, _y, width, _height in weighted) / len(weighted)
            confidence = 1.0
        elif prior_gray is not None:
            difference = cv2.absdiff(gray, prior_gray)
            _minimum, maximum, _min_location, max_location = cv2.minMaxLoc(
                cv2.GaussianBlur(difference, (31, 31), 0)
            )
            focus_x = float(max_location[0]) if maximum > 8 else frame_width / 2
            confidence = min(0.7, float(maximum) / 128)
        else:
            focus_x = frame_width / 2
        points.append(CropKeyframe(time - start, focus_x - crop_width / 2, confidence))
        prior_gray = gray
        time += sample_seconds
    capture.release()
    if not points:
        points = [CropKeyframe(0.0, (frame_width - crop_width) / 2, 0.0)]
    return smooth_keyframes(points, frame_width, crop_width)


def crop_expression(points: list[CropKeyframe]) -> str:
    if not points:
        return "(in_w-out_w)/2"
    expression = f"{points[-1].x:.3f}"
    for index in reversed(range(len(points) - 1)):
        point = points[index]
        next_point = points[index + 1]
        duration = max(0.001, next_point.time - point.time)
        interpolation = (
            f"{point.x:.3f}+({next_point.x:.3f}-{point.x:.3f})*(t-{point.time:.3f})/{duration:.3f}"
        )
        expression = f"if(lt(t,{next_point.time:.3f}),{interpolation},{expression})"
    return expression


def _clamp(value: float, maximum: float) -> float:
    return max(0.0, min(maximum, value))
