"""Import the repository's attributed GLB assets into the Unreal project.

Run with UnrealEditor-Cmd.exe and -ExecutePythonScript. The importer writes only
under /Game/Aegis/Imported so it can be re-run safely without touching the map.
"""

from pathlib import Path

import unreal


PROJECT_DIR = Path(unreal.Paths.project_dir()).resolve()
REPOSITORY_DIR = PROJECT_DIR.parents[1]
SOURCE_DIR = REPOSITORY_DIR / "anti-drone-dome" / "assets"
DESTINATION_ROOT = "/Game/Aegis/Imported"

IMPORTS = (
    (
        SOURCE_DIR / "80_followers_iranian_shahed-136_drone.glb",
        f"{DESTINATION_ROOT}/Shahed136",
    ),
    (
        SOURCE_DIR / "rts_radar_tower (1).glb",
        f"{DESTINATION_ROOT}/RadarTower",
    ),
)


def import_asset(source: Path, destination: str) -> list[str]:
    if not source.is_file():
        raise RuntimeError(f"Missing source asset: {source}")

    unreal.EditorAssetLibrary.make_directory(destination)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("save", True)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = list(task.get_editor_property("imported_object_paths"))
    if not imported:
        raise RuntimeError(f"Unreal imported no objects from {source.name}")
    unreal.log(f"AEGIS imported {source.name}: {imported}")
    return imported


def configure_for_gtx_1650(asset_path: str) -> None:
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if isinstance(asset, unreal.Texture2D):
        # The target GPU has 4 GB VRAM. Preserve streaming and cap authored
        # textures at 2K without modifying the attributed source GLBs.
        asset.set_editor_property("max_texture_size", 2048)
        asset.set_editor_property("never_stream", False)
        unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)
    elif isinstance(asset, unreal.StaticMesh):
        try:
            nanite_settings = asset.get_editor_property("nanite_settings")
            nanite_settings.enabled = False
            asset.set_editor_property("nanite_settings", nanite_settings)
        except Exception as exc:
            unreal.log_warning(f"Could not disable Nanite for {asset_path}: {exc}")
        unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)


def main() -> None:
    imported_paths: list[str] = []
    for source, destination in IMPORTS:
        imported_paths.extend(import_asset(source, destination))

    for asset_path in unreal.EditorAssetLibrary.list_assets(
        DESTINATION_ROOT, recursive=True, include_folder=False
    ):
        configure_for_gtx_1650(asset_path)

    unreal.EditorAssetLibrary.save_directory(
        DESTINATION_ROOT, only_if_is_dirty=False, recursive=True
    )
    unreal.log(f"AEGIS curated asset import complete ({len(imported_paths)} objects)")


if __name__ == "__main__":
    main()
