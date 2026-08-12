# Camera swap qualification

1. Record camera make, serial/identity, transport, lens, host, and driver version.
2. Enumerate devices and sweep every advertised format, resolution, frame rate, and
   compression. Store the enumeration artifact.
3. Select a mode, measure FOV with `fov-measurement.md`, and retain the raw result.
4. In a bright, documented scene, lock a short exposure and run the latency procedure
   for each candidate mode. Record exposure and lighting; do not call the result a
   device-only property.
5. Rerun the synthetic pixel-width sweep with the exact model hash and crop/tile
   configuration. Then update the parameter register only with the linked artifact.
6. Reconfigure the pipeline by editing its camera configuration only. The detector,
   tracker, and measurement code must remain unchanged; run `test_perception_pipeline.py`.

No camera is qualified for field use by this procedure. It establishes a replayable
host/mode configuration and explicitly identifies still-unmeasured target-device work.
