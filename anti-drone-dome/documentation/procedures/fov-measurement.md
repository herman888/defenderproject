# Field-of-view and centre-resolution procedure

Measure full-frame FOV and centre pixels-per-degree separately. A wide lens can
have strong barrel distortion; only the centre figure feeds centre-crop target
pixel estimates.

## Full-frame FOV

Mount the camera facing a flat wall. Measure front-of-lens to wall distance to
the centimetre. Move two markers to the exact left/right live-frame edges and
measure separation; repeat vertically. Repeat at a second distance at least
twice as far. Reject both measurements if either angular result differs by more
than 3 degrees; do not average a failed pair.

## Centre pixels per degree

Place a known-width object near the optical axis, within the central fifth of
the frame. Measure its distance, capture, and click its two edges. Repeat at a
second distance and apply the same 3-degree-equivalent agreement criterion.

If a checkerboard is available, capture at least 20 views across corners and
angles and store `calibrateCamera` matrix, distortion coefficients, and
reprojection error separately. Otherwise record intrinsics as **NOT MEASURED**
and label FOV results uncorrected for distortion.
