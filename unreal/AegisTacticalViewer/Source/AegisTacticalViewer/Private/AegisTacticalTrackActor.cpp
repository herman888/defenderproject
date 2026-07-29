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
    Label->SetWorldSize(105.0f);
    Label->SetRelativeLocation(FVector(0.0, 0.0, 260.0));
    Label->SetRelativeScale3D(FVector(0.8f, 0.8f, 0.8f));

    Trail = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Trail"));
    Trail->SetupAttachment(Visual);
    Trail->SetCollisionEnabled(ECollisionEnabled::NoCollision);

    MainWing = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MainWing"));
    MainWing->SetupAttachment(Visual);
    TailWing = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TailWing"));
    TailWing->SetupAttachment(Visual);
    VerticalFin = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("VerticalFin"));
    VerticalFin->SetupAttachment(Visual);
    for (int32 Index = 0; Index < 4; ++Index)
    {
        UStaticMeshComponent* RotorArm = CreateDefaultSubobject<UStaticMeshComponent>(
            *FString::Printf(TEXT("RotorArm%d"), Index));
        RotorArm->SetupAttachment(Visual);
        RotorArm->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        RotorArms.Add(RotorArm);
    }

    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(
        TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    if (Sphere.Succeeded())
    {
        Visual->SetStaticMesh(Sphere.Object);
        Trail->SetStaticMesh(Sphere.Object);
    }
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(
        TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cone(
        TEXT("/Engine/BasicShapes/Cone.Cone"));
    if (Cube.Succeeded())
    {
        MainWing->SetStaticMesh(Cube.Object);
        TailWing->SetStaticMesh(Cube.Object);
        VerticalFin->SetStaticMesh(Cube.Object);
        for (UStaticMeshComponent* RotorArm : RotorArms)
        {
            RotorArm->SetStaticMesh(Cube.Object);
        }
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
    const FString VisualKey = Snapshot.AssetId + TEXT("|") + Snapshot.Role + TEXT("|") + Snapshot.Type;
    if (AppliedVisualKey == VisualKey)
    {
        return;
    }
    AppliedVisualKey = VisualKey;

    const bool bIsInterceptor = Snapshot.Role.Equals(TEXT("interceptor"), ESearchCase::IgnoreCase)
        || Snapshot.AssetId.Contains(TEXT("interceptor"), ESearchCase::IgnoreCase);
    const bool bUsesEngineFallback = Definition.MeshPath.GetAssetPathString().StartsWith(
        TEXT("/Engine/BasicShapes"));
    for (UStaticMeshComponent* Detail : RotorArms)
    {
        Detail->SetHiddenInGame(true);
    }
    MainWing->SetHiddenInGame(true);
    TailWing->SetHiddenInGame(true);
    VerticalFin->SetHiddenInGame(true);
    SetActorScale3D(FVector::OneVector);

    if (!bUsesEngineFallback)
    {
        if (UStaticMesh* Mesh = Cast<UStaticMesh>(Definition.MeshPath.TryLoad()))
        {
            Visual->SetStaticMesh(Mesh);
            Visual->SetRelativeRotation(FRotator::ZeroRotator);
            Visual->SetRelativeScale3D(Definition.Scale);
        }
    }
    else if (bIsInterceptor)
    {
        // A compact quad silhouette: central fuselage plus four crossed arms.
        Visual->SetRelativeRotation(FRotator::ZeroRotator);
        Visual->SetRelativeScale3D(FVector(1.35f, 1.35f, 0.65f));
        for (int32 Index = 0; Index < RotorArms.Num(); ++Index)
        {
            UStaticMeshComponent* Arm = RotorArms[Index];
            Arm->SetHiddenInGame(false);
            Arm->SetRelativeLocation(FVector::ZeroVector);
            Arm->SetRelativeRotation(FRotator(0.0f, Index % 2 == 0 ? 45.0f : -45.0f, 0.0f));
            Arm->SetRelativeScale3D(FVector(2.8f, 0.13f, 0.10f));
        }
    }
    else
    {
        // A restrained fixed-wing fallback, replacing the former oversized box.
        const FSoftObjectPath ConePath(TEXT("/Engine/BasicShapes/Cone.Cone"));
        if (UStaticMesh* Cone = Cast<UStaticMesh>(ConePath.TryLoad()))
        {
            Visual->SetStaticMesh(Cone);
        }
        Visual->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));
        Visual->SetRelativeScale3D(FVector(1.05f, 1.05f, 3.4f));
        MainWing->SetHiddenInGame(false);
        MainWing->SetRelativeLocation(FVector(-55.0f, 0.0f, 0.0f));
        MainWing->SetRelativeScale3D(FVector(0.45f, 5.4f, 0.13f));
        TailWing->SetHiddenInGame(false);
        TailWing->SetRelativeLocation(FVector(-210.0f, 0.0f, 18.0f));
        TailWing->SetRelativeScale3D(FVector(0.25f, 1.7f, 0.10f));
        VerticalFin->SetHiddenInGame(false);
        VerticalFin->SetRelativeLocation(FVector(-220.0f, 0.0f, 72.0f));
        VerticalFin->SetRelativeScale3D(FVector(0.35f, 0.12f, 0.8f));
    }
    BaseColor = Definition.BaseColor;
    Label->SetText(FText::FromString(Definition.Label + TEXT("  ") + Snapshot.Id));
    SetDisplayColor(BaseColor);
}

void AAegisTacticalTrackActor::SetDisplayColor(const FLinearColor& Color)
{
    if (ShapeMaterial != nullptr && DynamicMaterial == nullptr)
    {
        DynamicMaterial = UMaterialInstanceDynamic::Create(ShapeMaterial, this);
        Visual->SetMaterial(0, DynamicMaterial);
        Trail->SetMaterial(0, DynamicMaterial);
        MainWing->SetMaterial(0, DynamicMaterial);
        TailWing->SetMaterial(0, DynamicMaterial);
        VerticalFin->SetMaterial(0, DynamicMaterial);
        for (UStaticMeshComponent* Detail : RotorArms)
        {
            Detail->SetMaterial(0, DynamicMaterial);
        }
    }
    if (DynamicMaterial != nullptr)
    {
        DynamicMaterial->SetVectorParameterValue(TEXT("Color"), Color);
    }
    Label->SetTextRenderColor(Color.ToFColor(true));
}

void AAegisTacticalTrackActor::AddTrailPoint(const FVector& WorldLocation)
{
    if (!TrailPoints.IsEmpty() && FVector::DistSquared(TrailPoints.Last(), WorldLocation) < 500.0f * 500.0f)
    {
        return;
    }
    TrailPoints.Add(WorldLocation);
    if (TrailPoints.Num() > 20)
    {
        TrailPoints.RemoveAt(0);
    }
    Trail->ClearInstances();
    for (int32 Index = 0; Index < TrailPoints.Num(); ++Index)
    {
        const float Scale = 0.08f + 0.12f * (static_cast<float>(Index + 1) / TrailPoints.Num());
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
