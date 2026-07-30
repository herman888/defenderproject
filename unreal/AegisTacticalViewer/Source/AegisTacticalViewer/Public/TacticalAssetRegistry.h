#pragma once

#include "CoreMinimal.h"

struct FTacticalVisualDefinition
{
    FString Label;
    FSoftObjectPath MeshPath;
    FVector Scale = FVector::OneVector;
    FLinearColor BaseColor = FLinearColor::White;
    /** Optional second mesh for authored models that contain separate shells. */
    FSoftObjectPath DetailMeshPath;
};

/**
 * Registry for authored Fab/Quixel replacements with deterministic engine
 * fallbacks. Imported assets placed under /Game/Aegis/Vehicles with the
 * documented names are picked up automatically without telemetry changes.
 */
class AEGISTACTICALVIEWER_API FTacticalAssetRegistry
{
public:
    static FTacticalVisualDefinition Resolve(
        const FString& AssetId, const FString& Role, const FString& Type);
};
