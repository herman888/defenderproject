#include "TacticalAssetRegistry.h"

namespace
{
const FSoftObjectPath SpherePath(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
const FSoftObjectPath CubePath(TEXT("/Engine/BasicShapes/Cube.Cube"));
const FSoftObjectPath ConePath(TEXT("/Engine/BasicShapes/Cone.Cone"));
}

FTacticalVisualDefinition FTacticalAssetRegistry::Resolve(
    const FString& AssetId, const FString& Role, const FString& Type)
{
    const FString Key = (AssetId + TEXT(" ") + Role + TEXT(" ") + Type).ToLower();
    if (Key.Contains(TEXT("interceptor")))
    {
        return {TEXT("INTERCEPTOR"), ConePath, FVector(2.0, 2.0, 6.0),
            FLinearColor(0.05f, 0.45f, 1.0f)};
    }
    if (Key.Contains(TEXT("shahed")))
    {
        return {TEXT("SHAHED-136"), CubePath, FVector(7.0, 18.0, 1.2),
            FLinearColor(1.0f, 0.12f, 0.06f)};
    }
    if (Key.Contains(TEXT("fpv")))
    {
        return {TEXT("FPV THREAT"), ConePath, FVector(1.6, 1.6, 3.6),
            FLinearColor(1.0f, 0.22f, 0.05f)};
    }
    if (Key.Contains(TEXT("quad")))
    {
        return {TEXT("QUAD THREAT"), SpherePath, FVector(3.0),
            FLinearColor(1.0f, 0.35f, 0.05f)};
    }
    return {Role.IsEmpty() ? TEXT("UNIDENTIFIED") : Role.ToUpper(), SpherePath,
        FVector(2.5), Role.Equals(TEXT("interceptor"), ESearchCase::IgnoreCase)
            ? FLinearColor(0.05f, 0.45f, 1.0f)
            : FLinearColor(1.0f, 0.15f, 0.05f)};
}
