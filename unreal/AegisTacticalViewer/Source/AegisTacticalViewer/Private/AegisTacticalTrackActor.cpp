#include "AegisTacticalTrackActor.h"

#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Math/RotationMatrix.h"
#include "TacticalAssetRegistry.h"
#include "UObject/ConstructorHelpers.h"

AAegisTacticalTrackActor::AAegisTacticalTrackActor()
{
    PrimaryActorTick.bCanEverTick = true;

    Visual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Visual"));
    RootComponent = Visual;
    Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Visual->SetCastShadow(true);
    SetActorHiddenInGame(true);

    Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
    Label->SetupAttachment(Visual);
    Label->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
    Label->SetWorldSize(140.0f);
    Label->SetRelativeLocation(FVector(0.0, 0.0, 360.0));

    Trail = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Trail"));
    Trail->SetupAttachment(Visual);
    Trail->SetCollisionEnabled(ECollisionEnabled::NoCollision);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(
        TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    if (Sphere.Succeeded())
    {
        Visual->SetStaticMesh(Sphere.Object);
    }
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMaterial(
        TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    if (BasicMaterial.Succeeded())
    {
        ShapeMaterial = BasicMaterial.Object;
    }
}

FVector AAegisTacticalTrackActor::EnuToUnrealWorld(const FVector& EnuMetres)
{
    // ENU metres -> Unreal centimetres under the project's X=N, Y=E, Z=U map.
    return FVector(EnuMetres.Y, EnuMetres.X, EnuMetres.Z) * 100.0;
}

FRotator AAegisTacticalTrackActor::EnuOrientationToUnreal(
    const FQuat& OrientationEnu, double HeadingDegrees)
{
    // Rotate both forward and up through the supplied ENU attitude, then change
    // basis once (ENU: E/N/U; Unreal: N/E/U). Heading is only a defensive
    // fallback for an invalid vector; it never replaces valid 3-D attitude.
    const FVector Forward = EnuToUnrealWorld(
        OrientationEnu.RotateVector(FVector::ForwardVector)).GetSafeNormal();
    const FVector Up = EnuToUnrealWorld(
        OrientationEnu.RotateVector(FVector::UpVector)).GetSafeNormal();
    if (Forward.IsNearlyZero() || Up.IsNearlyZero())
    {
        return FRotator(0.0, HeadingDegrees, 0.0);
    }
    return FRotationMatrix::MakeFromXZ(Forward, Up).Rotator();
}

void AAegisTacticalTrackActor::ApplyVisualDefinition(
    const FTacticalTrackSnapshot& Snapshot)
{
    const FTacticalVisualDefinition Definition = FTacticalAssetRegistry::Resolve(
        Snapshot.AssetId, Snapshot.Role, Snapshot.Type);
    if (UStaticMesh* Mesh = Cast<UStaticMesh>(Definition.MeshPath.TryLoad()))
    {
        Visual->SetStaticMesh(Mesh);
        Trail->SetStaticMesh(Mesh);
    }
    const bool bFlightAlignedCone = Snapshot.Role.Equals(TEXT("interceptor"), ESearchCase::IgnoreCase)
        || Snapshot.Type.Contains(TEXT("fpv"), ESearchCase::IgnoreCase);
    // Engine's basic cone points upward; rotate it into the actor's forward axis.
    Visual->SetRelativeRotation(bFlightAlignedCone ? FRotator(0.0f, 90.0f, 0.0f)
        : FRotator::ZeroRotator);
    SetActorScale3D(Definition.Scale);
    BaseColor = Definition.BaseColor;
    Label->SetText(FText::FromString(Definition.Label + TEXT(" // ") + Snapshot.Id));
    SetDisplayColor(BaseColor);
}

void AAegisTacticalTrackActor::SetDisplayColor(const FLinearColor& Color)
{
    if (ShapeMaterial != nullptr && DynamicMaterial == nullptr)
    {
        DynamicMaterial = UMaterialInstanceDynamic::Create(ShapeMaterial, this);
        Visual->SetMaterial(0, DynamicMaterial);
        Trail->SetMaterial(0, DynamicMaterial);
    }
    if (DynamicMaterial != nullptr)
    {
        DynamicMaterial->SetVectorParameterValue(TEXT("Color"), Color);
    }
    Label->SetTextRenderColor(Color.ToFColor(true));
}

void AAegisTacticalTrackActor::AddTrailPoint(const FVector& WorldLocation)
{
    if (!TrailPoints.IsEmpty() && FVector::DistSquared(TrailPoints.Last(), WorldLocation) < 250.0f * 250.0f)
    {
        return;
    }
    TrailPoints.Add(WorldLocation);
    if (TrailPoints.Num() > 32)
    {
        TrailPoints.RemoveAt(0);
    }
    Trail->ClearInstances();
    for (int32 Index = 0; Index < TrailPoints.Num(); ++Index)
    {
        const float Scale = 0.045f + 0.11f * (static_cast<float>(Index + 1) / TrailPoints.Num());
        Trail->AddInstance(
            FTransform(FRotator::ZeroRotator, TrailPoints[Index], FVector(Scale)), true);
    }
}

void AAegisTacticalTrackActor::ApplySnapshot(const FTacticalTrackSnapshot& Snapshot)
{
    TrackRole = Snapshot.Role;
    ApplyVisualDefinition(Snapshot);
    TargetLocation = EnuToUnrealWorld(Snapshot.PositionEnuMetres);
    TargetRotation = EnuOrientationToUnreal(
        Snapshot.OrientationEnu, Snapshot.HeadingDegrees);
    LastSnapshotTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
    bIsStale = false;
    bAbsent = false;
    SetActorHiddenInGame(false);
    AddTrailPoint(TargetLocation);
}

void AAegisTacticalTrackActor::MarkAbsent()
{
    bAbsent = true;
    bIsStale = true;
    TrailPoints.Reset();
    Trail->ClearInstances();
    SetActorHiddenInGame(true);
}

void AAegisTacticalTrackActor::SetLinkStale(bool bLinkStale)
{
    if (bLastLinkStale == bLinkStale)
    {
        return;
    }
    bLastLinkStale = bLinkStale;
    SetDisplayColor(bLinkStale ? FLinearColor(1.0f, 0.62f, 0.02f) : BaseColor);
}

void AAegisTacticalTrackActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);

    const UWorld* World = GetWorld();
    if (World == nullptr)
    {
        return;
    }

    bIsStale = bAbsent || World->GetTimeSeconds() - LastSnapshotTime > StaleAfterSeconds;
    if (bIsStale)
    {
        SetLinkStale(true);
        // Do not extrapolate a lost tactical track.
        return;
    }
    SetLinkStale(false);

    SetActorLocation(FMath::VInterpTo(
        GetActorLocation(), TargetLocation, DeltaSeconds, 12.0f));
    SetActorRotation(FMath::RInterpTo(
        GetActorRotation(), TargetRotation, DeltaSeconds, 12.0f));
}
