#pragma once

#include "CoreMinimal.h"

struct FTacticalVisualDefinition
{
    FString Label;
    FSoftObjectPath MeshPath;
    FVector Scale = FVector::OneVector;
    FLinearColor BaseColor = FLinearColor::White;
};

/**
 * Registry for authored Fab/Quixel replacements with deterministic engine
 * fallbacks. Imported assets can be configured by replacing the matching
 * object paths in this class without changing telemetry semantics.
 */
class AEGISTACTICALVIEWER_API FTacticalAssetRegistry
{
public:
    static FTacticalVisualDefinition Resolve(
        const FString& AssetId, const FString& Role, const FString& Type);
};
