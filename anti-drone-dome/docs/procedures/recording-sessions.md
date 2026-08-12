# Recording sessions

Each video clip has a JSON sidecar using `larp.recording-session.v1` with: UTC start
and end, operator, camera identity and serial, lens, mode, resolution, FPS, exposure,
gain, crop, FOV artifact, location class, weather/lighting, target type, marked range
method and values, and whether the clip is training, validation, or held-out.

Name clips `YYYYMMDDThhmmssZ_<camera>_<mode>_<range-m>_<split>_<sequence>.<ext>`;
the sidecar has the same basename. Use UTC and never encode a claim such as a measured
range when the range is estimated.

Held-out evaluation clips must be recorded at marked ranges, marked `held-out` before
review, and never viewed or tuned against during training/threshold/crop selection.
If this rule is broken, relabel the clip development-only and record the reason.
