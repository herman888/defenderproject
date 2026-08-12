# Camera FOV measurement

Measure rather than infer the field of view from a lens listing. Mount the camera
rigidly and level; lock the selected mode, focus, exposure, and crop configuration.

1. Place a planar target of known width at two marked distances, each measured from
   the sensor plane. Record the target width, both distances, image dimensions, and
   the measured target pixel width.
2. Calculate horizontal full-frame FOV independently at each distance using the
   observed scene width. Record each result and their agreement. The reported value
   is `NOT MEASURED` if they differ by more than 2 degrees or 5%, whichever is
   larger; investigate target placement, distortion, or focus before retrying.
3. Measure centre pixels-per-degree separately: move a marked target through a
   known small angle about the camera centre and divide pixel displacement by angle.
   Do not derive this from edge FOV on a wide lens.
4. If a checkerboard is available, record the board dimensions, image set, reprojection
   error, and fitted intrinsics/distortion. This supplements rather than replaces the
   two-distance check.

Write a versioned artifact with camera identity, mode, resolution, FOV, centre
pixels-per-degree, crop configuration, raw measurements, operator, and rejection
decision. Values are `NOT MEASURED` until this run is complete.
