# Glass-to-glass latency procedure

This Windows-only procedure measures scene-change to frame availability in
userspace. It is not capture-to-detection or a guidance-loop budget.

1. Remove props and disconnect the flight battery. Mount the Innomaker rigidly,
   0.5 m from the monitor; do not hand-hold it.
2. Dim the room (not black), fill the central third of the camera frame with
   monitor only, focus and lock focus. Record the lighting condition.
3. Record monitor resolution/refresh rate; disable VRR, motion smoothing, and
   power saving. Close other applications and select Windows High Performance.
4. Run 50 trials each for 1080p MJPEG, 640x480 YUY2, 720p MJPEG, then repeat
   1080p MJPEG as the drift check. The script waits for operator confirmation.
5. Reject a run with fewer than 45 crossings. Reject both 1080p runs if their
   p50 values differ by over 15%. Flag (do not reinterpret) a 640x480 p50 not
   lower than 1080p.

Artifacts retain every sample and include unseparated monitor refresh/response,
exposure integration, and OpenCV scheduling bias. None is silently subtracted.
