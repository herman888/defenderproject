#include "TacticalAssetRegistry.h"

#include "Misc/PackageName.h"

namespace
{
const FSoftObjectPath SpherePath(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
const FSoftObjectPath CubePath(TEXT("/Engine/BasicShapes/Cube.Cube"));
const FSoftObjectPath ConePath(TEXT("/Engine/BasicShapes/Cone.Cone"));

FSoftObjectPath AuthoredOrFallback(
    const TCHAR* AuthoredPath, const FSoftObjectPath& Fallback)
{
    const FSoftObjectPath Candidate(AuthoredPath);
    if (!FPackageName::DoesPackageExist(Candidate.GetLongPackageName()))
    {
        return Fallback;
    }
    return Candidate.ResolveObject() != nullptr || Candidate.TryLoad() != nullptr
        ? Candidate : Fallback;
}
}

FTacticalVisualDefinition FTacticalAssetRegistry::Resolve(
    const FString& AssetId, const FString& Role, const FString& Type)
{
    const FString Key = (AssetId + TEXT(" ") + Role + TEXT(" ") + Type).ToLower();
    if (Key.Contains(TEXT("interceptor")))
    {
        return {TEXT("INTERCEPTOR"), AuthoredOrFallback(
                TEXT("/Game/Aegis/Vehicles/SM_Interceptor.SM_Interceptor"), ConePath),
            FVector(2.0, 2.0, 6.0),
            FLinearColor(0.05f, 0.45f, 1.0f)};
    }
    if (Key.Contains(TEXT("shahed")))
    {
        return {TEXT("SHAHED-136"), AuthoredOrFallback(
                TEXT("/Game/Aegis/Vehicles/SM_Shahed136.SM_Shahed136"), CubePath),
            FVector(7.0, 18.0, 1.2),
            FLinearColor(1.0f, 0.12f, 0.06f)};
    }
    if (Key.Contains(TEXT("fpv")))
    {
        return {TEXT("FPV THREAT"), AuthoredOrFallback(
                TEXT("/Game/Aegis/Vehicles/SM_FpvThreat.SM_FpvThreat"), ConePath),
            FVector(1.6, 1.6, 3.6),
            FLinearColor(1.0f, 0.22f, 0.05f)};
    }
    if (Key.Contains(TEXT("quad")))
    {
        return {TEXT("QUAD THREAT"), AuthoredOrFallback(
                TEXT("/Game/Aegis/Vehicles/SM_ConsumerQuad.SM_ConsumerQuad"), SpherePath),
            FVector(3.0),
            FLinearColor(1.0f, 0.35f, 0.05f)};
    }
    return {Role.IsEmpty() ? TEXT("UNIDENTIFIED") : Role.ToUpper(), SpherePath,
        FVector(2.5), Role.Equals(TEXT("interceptor"), ESearchCase::IgnoreCase)
            ? FLinearColor(0.05f, 0.45f, 1.0f)
            : FLinearColor(1.0f, 0.15f, 0.05f)};
}
