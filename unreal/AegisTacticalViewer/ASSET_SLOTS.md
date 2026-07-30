# AEGIS vehicle asset slots

The viewer automatically uses these static meshes when they exist:

- `/Game/Aegis/Vehicles/SM_Shahed136`
- `/Game/Aegis/Vehicles/SM_Interceptor`
- `/Game/Aegis/Vehicles/SM_FpvThreat`
- `/Game/Aegis/Vehicles/SM_ConsumerQuad`

Until then, low-cost procedural silhouettes remain active. Imported meshes are
presentation assets only: Python telemetry continues to own position, attitude,
speed, sensing, guidance, and mission outcome.

For the GTX 1650 target, use 2K materials, authored LODs, simple collision (or
no collision for display tracks), and avoid Nanite-only meshes.
