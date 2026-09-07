from clipper.reframe import CropKeyframe, crop_dimensions, crop_expression, smooth_keyframes


def test_vertical_crop_dimensions_preserve_nine_by_sixteen() -> None:
    assert crop_dimensions(1920, 1080) == (608, 1080)
    assert crop_dimensions(1280, 720) == (405, 720)


def test_crop_tracking_is_clamped_and_damped() -> None:
    points = [
        CropKeyframe(time=0, x=0, confidence=1),
        CropKeyframe(time=1, x=1000, confidence=1),
        CropKeyframe(time=2, x=1900, confidence=1),
    ]

    smoothed = smooth_keyframes(points, frame_width=1920, crop_width=608, smoothing=0.5)

    assert all(0 <= point.x <= 1312 for point in smoothed)
    assert smoothed[1].x == 500
    assert smoothed[2].x == 906


def test_crop_expression_interpolates_smoothly_between_samples() -> None:
    points = [
        CropKeyframe(time=0, x=100, confidence=1),
        CropKeyframe(time=1, x=200, confidence=1),
        CropKeyframe(time=2, x=300, confidence=1),
    ]

    expression = crop_expression(points)

    assert "(200.000-100.000)*(t-0.000)/1.000" in expression
    assert "(300.000-200.000)*(t-1.000)/1.000" in expression
    assert expression.endswith("300.000))")
