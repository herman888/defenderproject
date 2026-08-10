#include "AegisTacticalSiteActor.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Math/RotationMatrix.h"
#include "UObject/SoftObjectPath.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
void ConfigureStatic(UStaticMeshComponent* Component, UStaticMesh* Mesh,
    UMaterialInterface* Material, const FLinearColor& Color)
{
    Component->SetStaticMesh(Mesh);
    Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Component->SetCastShadow(true);
    if (Material != nullptr)
    {
        UMaterialInstanceDynamic* Dynamic = UMaterialInstanceDynamic::Create(Material, Component);
        Dynamic->SetVectorParameterValue(TEXT("Color"), Color);
        Component->SetMaterial(0, Dynamic);
    }
}

void ConfigureInstances(UInstancedStaticMeshComponent* Component, UStaticMesh* Mesh,
    UMaterialInterface* Material, const FLinearColor& Color)
{
    Component->SetStaticMesh(Mesh);
    Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Component->SetCastShadow(true);
    if (Material != nullptr)
    {
        UMaterialInstanceDynamic* Dynamic = UMaterialInstanceDynamic::Create(Material, Component);
        Dynamic->SetVectorParameterValue(TEXT("Color"), Color);
        Component->SetMaterial(0, Dynamic);
    }
}
}

AAegisTacticalSiteActor::AAegisTacticalSiteActor()
{
    // The rotating antenna is visual context only. Python remains the sole
    // authority for radar sensing and all mission state.
    PrimaryActorTick.bCanEverTick = true;
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    RootComponent = SceneRoot;
    SitePad = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SitePad"));
    SitePad->SetupAttachment(SceneRoot);
    SensorTower = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SensorTower"));
    SensorTower->SetupAttachment(SceneRoot);
    SensorDome = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SensorDome"));
    SensorDome->SetupAttachment(SceneRoot);
    RadarAntenna = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RadarAntenna"));
    RadarAntenna->SetupAttachment(SceneRoot);
    RadarPulse = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RadarPulse"));
    RadarPulse->SetupAttachment(SceneRoot);
    SensorSightline = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("SensorSightline"));
    SensorSightline->SetupAttachment(SceneRoot);
    PerimeterMarker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PerimeterMarker"));
    PerimeterMarker->SetupAttachment(SceneRoot);
    SiteLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("SiteLabel"));
    SiteLabel->SetupAttachment(SceneRoot);
    InterceptMarker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("InterceptMarker"));
    InterceptMarker->SetupAttachment(SceneRoot);
    InterceptBeacon = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("InterceptBeacon"));
    InterceptBeacon->SetupAttachment(SceneRoot);
    InterceptLadder = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("InterceptLadder"));
    InterceptLadder->SetupAttachment(SceneRoot);
    CompoundBuildings = CreateDefaultSubobject<UInstancedStaticMeshComponent>(
        TEXT("CompoundBuildings"));
    CompoundBuildings->SetupAttachment(SceneRoot);
    AccessRoad = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("AccessRoad"));
    AccessRoad->SetupAttachment(SceneRoot);
    PerimeterFence = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("PerimeterFence"));
    PerimeterFence->SetupAttachment(SceneRoot);
    Vegetation = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Vegetation"));
    Vegetation->SetupAttachment(SceneRoot);
    RockScatter = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("RockScatter"));
    RockScatter->SetupAttachment(SceneRoot);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cone(TEXT("/Engine/BasicShapes/Cone.Cone"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMaterial(
        TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    if (Cylinder.Succeeded() && Sphere.Succeeded())
    {
        ConfigureStatic(SitePad, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.06f, 0.12f, 0.16f));
        ConfigureStatic(SensorTower, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.32f, 0.38f, 0.42f));
        ConfigureStatic(SensorDome, Sphere.Object, BasicMaterial.Object, FLinearColor(0.12f, 0.65f, 0.68f));
        ConfigureStatic(RadarAntenna, Cube.Object, BasicMaterial.Object, FLinearColor(0.14f, 0.76f, 0.78f));
        ConfigureStatic(RadarPulse, Sphere.Object, BasicMaterial.Object, FLinearColor(0.12f, 0.85f, 0.76f));
        ConfigureInstances(SensorSightline, Cylinder.Object, BasicMaterial.Object,
            FLinearColor(0.10f, 0.95f, 0.58f));
        SensorSightline->SetCastShadow(false);
        SensorSightline->SetVisibility(false);
        SightlineMaterial = Cast<UMaterialInstanceDynamic>(SensorSightline->GetMaterial(0));
        ConfigureStatic(InterceptMarker, Sphere.Object, BasicMaterial.Object, FLinearColor(1.0f, 0.72f, 0.10f));
        ConfigureStatic(InterceptBeacon, Cube.Object, BasicMaterial.Object, FLinearColor(1.0f, 0.72f, 0.10f));
        ConfigureInstances(InterceptLadder, Cube.Object, BasicMaterial.Object, FLinearColor(1.0f, 0.72f, 0.10f));
        InterceptLadder->SetCastShadow(false);
        LadderMaterial = Cast<UMaterialInstanceDynamic>(InterceptLadder->GetMaterial(0));
        InterceptMaterial = Cast<UMaterialInstanceDynamic>(InterceptMarker->GetMaterial(0));
        InterceptBeacon->SetMaterial(0, InterceptMaterial);
    }
    ConfigureInstances(CompoundBuildings, Cube.Object, BasicMaterial.Object,
        FLinearColor(0.16f, 0.22f, 0.25f));
    ConfigureInstances(AccessRoad, Cube.Object, BasicMaterial.Object,
        FLinearColor(0.07f, 0.08f, 0.08f));
    ConfigureInstances(PerimeterFence, Cube.Object, BasicMaterial.Object,
        FLinearColor(0.28f, 0.34f, 0.34f));
    ConfigureInstances(RockScatter, Sphere.Object, BasicMaterial.Object,
        FLinearColor(0.24f, 0.22f, 0.18f));
    ConfigureInstances(Vegetation, Cone.Object, BasicMaterial.Object,
        FLinearColor(0.10f, 0.21f, 0.14f));
    SitePad->SetRelativeScale3D(FVector(24.0f, 24.0f, 0.12f));
    // RadarNode is at local ENU (0, 0, 10 m).  Keep the visual antenna at
    // that same height: Unreal uses centimetres.
    SensorTower->SetRelativeLocation(FVector(0.0f, 0.0f, 500.0f));
    SensorTower->SetRelativeScale3D(FVector(0.8f, 0.8f, 5.0f));
    SensorDome->SetRelativeLocation(FVector(0.0f, 0.0f, 1025.0f));
    SensorDome->SetRelativeScale3D(FVector(1.35f, 1.35f, 0.7f));
    RadarAntenna->SetRelativeLocation(FVector(0.0f, 0.0f, 1110.0f));
    RadarAntenna->SetRelativeScale3D(FVector(4.0f, 0.18f, 0.12f));
    RadarPulse->SetRelativeLocation(FVector(0.0f, 0.0f, 1110.0f));
    RadarPulse->SetRelativeScale3D(FVector(0.1f, 0.1f, 0.015f));
    RadarPulse->SetCastShadow(false);

    // Prefer the attributed RTS radar tower when it has been imported. The
    // lightweight procedural antenna remains separate so it can rotate without
    // adding skeletal-animation cost to the display client.
    const FSoftObjectPath AuthoredTowerPath(
        TEXT("/Game/Aegis/Imported/RadarTower/rts_radar_tower__1_/"
             "StaticMeshes/radar_tower_build_0.radar_tower_build_0"));
    if (UStaticMesh* AuthoredTower = Cast<UStaticMesh>(AuthoredTowerPath.TryLoad()))
    {
        SensorTower->SetStaticMesh(AuthoredTower);
        SensorTower->EmptyOverrideMaterials();
        const FBoxSphereBounds Bounds = AuthoredTower->GetBounds();
        const float FullHeight = FMath::Max(Bounds.BoxExtent.Z * 2.0f, 1.0f);
        const float TowerScale = 1000.0f / FullHeight;
        SensorTower->SetRelativeScale3D(FVector(TowerScale));
        SensorTower->SetRelativeLocation(FVector(
            0.0f, 0.0f, -(Bounds.Origin.Z - Bounds.BoxExtent.Z) * TowerScale));
        SensorDome->SetHiddenInGame(true);
    }

    // A lightweight generic compound gives scale and spatial context before
    // licensed art assets are assigned. These are instanced primitives, so the
    // complete dressing remains inexpensive on a 4 GB GTX 1650.
    const FTransform Buildings[] = {
        FTransform(FRotator(0, 12, 0), FVector(1700, 900, 230), FVector(8.0f, 4.8f, 2.3f)),
        FTransform(FRotator(0, -8, 0), FVector(-1500, 1100, 180), FVector(5.5f, 4.2f, 1.8f)),
        FTransform(FRotator(0, 0, 0), FVector(1600, -1100, 145), FVector(4.0f, 3.2f, 1.45f)),
        FTransform(FRotator(0, 90, 0), FVector(-1600, -900, 130), FVector(3.2f, 5.0f, 1.3f)),
    };
    for (const FTransform& Transform : Buildings)
    {
        CompoundBuildings->AddInstance(Transform);
    }
    for (int32 Index = 0; Index < 8; ++Index)
    {
        AccessRoad->AddInstance(FTransform(
            FRotator(0, 0, 0), FVector(2550, -2800 - Index * 1250, 8),
            FVector(4.2f, 7.0f, 0.08f)));
    }
    PerimeterFence->AddInstance(FTransform(
        FRotator::ZeroRotator, FVector(0, 3550, 70), FVector(35.0f, 0.08f, 0.7f)));
    PerimeterFence->AddInstance(FTransform(
        FRotator::ZeroRotator, FVector(0, -3550, 70), FVector(35.0f, 0.08f, 0.7f)));
    PerimeterFence->AddInstance(FTransform(
        FRotator::ZeroRotator, FVector(3550, 0, 70), FVector(0.08f, 35.0f, 0.7f)));
    PerimeterFence->AddInstance(FTransform(
        FRotator::ZeroRotator, FVector(-3550, 0, 70), FVector(0.08f, 35.0f, 0.7f)));

    const FVector FoliageLocations[] = {
        FVector(4700, 4200, 145), FVector(-4800, 3900, 180),
        FVector(5200, -3500, 130), FVector(-5200, -4100, 165),
        FVector(6100, 800, 140), FVector(-6200, 1200, 175),
        FVector(2300, 5200, 135), FVector(-1800, -5700, 155),
        FVector(7000, -2200, 125), FVector(-6900, 2700, 160),
    };
    for (int32 Index = 0; Index < UE_ARRAY_COUNT(FoliageLocations); ++Index)
    {
        const float Scale = 2.1f + (Index % 3) * 0.45f;
        Vegetation->AddInstance(FTransform(
            FRotator(0, Index * 31.0f, 0), FoliageLocations[Index],
            FVector(Scale * 0.55f, Scale * 0.55f, Scale)));
    }
    const FVector RockLocations[] = {
        FVector(4300, 2100, 45), FVector(-4000, 2900, 55),
        FVector(3900, -2600, 40), FVector(-4500, -1900, 65),
        FVector(6000, 4200, 50), FVector(-6100, -3600, 45),
    };
    for (int32 Index = 0; Index < UE_ARRAY_COUNT(RockLocations); ++Index)
    {
        RockScatter->AddInstance(FTransform(
            FRotator(0, Index * 43.0f, 0), RockLocations[Index],
            FVector(1.1f + Index * 0.08f, 0.8f, 0.65f)));
    }

    // This was an opaque 104 m green disc, which looked like a pool on the
    // terrain. A radius is a tactical concept, not a solid physical object.
    PerimeterMarker->SetVisibility(false);
    PerimeterMarker->SetHiddenInGame(true);

    SiteLabel->SetText(FText::FromString(TEXT("PROTECTED TRAINING SITE")));
    SiteLabel->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
    SiteLabel->SetTextRenderColor(FColor(122, 224, 222));
    SiteLabel->SetWorldSize(150.0f);
    SiteLabel->SetRelativeLocation(FVector(0.0f, 0.0f, 1450.0f));
    InterceptMarker->SetVisibility(false);
    InterceptBeacon->SetVisibility(false);
    InterceptLadder->SetVisibility(false);
}

void AAegisTacticalSiteActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    MarkerPulseSeconds += DeltaSeconds;
    if (RadarAntenna != nullptr)
    {
        RadarAntenna->AddLocalRotation(FRotator(0.0f,
            (bRadarFailed ? 6.0f : (bRadarLocked ? 58.0f : 34.0f)) * DeltaSeconds, 0.0f));
    }
    if (RadarPulse != nullptr)
    {
        const float Phase = FMath::Fmod(MarkerPulseSeconds * (bRadarLocked ? 1.4f : 0.75f), 1.0f);
        const float Radius = bRadarFailed ? 0.05f : FMath::Lerp(0.8f, 22.0f, Phase);
        RadarPulse->SetRelativeScale3D(FVector(Radius, Radius, 0.012f));
        RadarPulse->SetVisibility(!bRadarFailed);
    }
    if (bMarkerVisible && InterceptMarker != nullptr)
    {
        // A small steady reticle. The previous 3.2 m pulsing sphere occluded
        // the engagement it was annotating; the dotted ladder below carries
        // the position cue instead, which reads cleanly against terrain.
        const float Pulse = 0.55f + 0.06f * FMath::Sin(MarkerPulseSeconds * 4.0f);
        InterceptMarker->SetRelativeScale3D(FVector(Pulse));
        InterceptBeacon->AddLocalRotation(FRotator(0.0f, 65.0f * DeltaSeconds, 0.0f));
    }
}

void AAegisTacticalSiteActor::SetSensorPresentationState(
    const bool bInRadarLocked, const bool bInRadarFailed)
{
    bRadarLocked = bInRadarLocked;
    bRadarFailed = bInRadarFailed;
    UpdateSensorSightline();
}

void AAegisTacticalSiteActor::SetSensorTrackPresentation(
    const FVector& PositionEnuMetres)
{
    // ENU metres to the viewer's local centimetre frame. This is intentionally
    // only a presentation cue: the sightline is shown *after* Python declares
    // radar lock and it never feeds state back to the simulation.
    SensorTrackWorld = FVector(
        PositionEnuMetres.Y * 100.0f,
        PositionEnuMetres.X * 100.0f,
        PositionEnuMetres.Z * 100.0f);
    bHasSensorTrack = true;
    UpdateSensorSightline();
}

void AAegisTacticalSiteActor::UpdateSensorSightline()
{
    if (SensorSightline == nullptr)
    {
        return;
    }
    SensorSightline->ClearInstances();
    const bool bVisible = bRadarLocked && !bRadarFailed && bHasSensorTrack;
    SensorSightline->SetVisibility(bVisible);
    if (!bVisible || RadarAntenna == nullptr)
    {
        return;
    }

    const FVector Origin = RadarAntenna->GetRelativeLocation();
    const FVector Delta = SensorTrackWorld - Origin;
    const float Distance = Delta.Length();
    if (Distance < KINDA_SMALL_NUMBER)
    {
        SensorSightline->SetVisibility(false);
        return;
    }

    // A dotted link reads as a tracked line of sight instead of the old opaque
    // green/orange balls. It is deliberately thick enough to survive a range
    // observer shot, while the bounded instance count stays appropriate for
    // the 4 GB target.
    const int32 DashCount = FMath::Clamp(FMath::RoundToInt(Distance / 2200.0f), 8, 30);
    const float Spacing = Distance / static_cast<float>(DashCount + 1);
    const float DashLength = FMath::Clamp(Spacing * 0.50f, 90.0f, 420.0f);
    const FRotator Rotation = FRotationMatrix::MakeFromZ(Delta.GetSafeNormal()).Rotator();
    for (int32 Index = 1; Index <= DashCount; ++Index)
    {
        const FVector Location = Origin + Delta.GetSafeNormal() * (Spacing * Index);
        SensorSightline->AddInstance(FTransform(
            Rotation, Location, FVector(0.55f, 0.55f, DashLength / 100.0f)));
    }
    if (SightlineMaterial != nullptr)
    {
        SightlineMaterial->SetVectorParameterValue(TEXT("Color"),
            FLinearColor(0.10f, 0.95f, 0.58f));
    }
}

void AAegisTacticalSiteActor::SetPredictedIntercept(
    const FVector& PositionEnuMetres, const bool bVisible, const FString& Status)
{
    bMarkerVisible = bVisible;
    InterceptMarker->SetVisibility(bVisible);
    InterceptBeacon->SetVisibility(bVisible);
    if (!bVisible)
    {
        InterceptLadder->SetVisibility(false);
        InterceptLadder->ClearInstances();
        return;
    }
    const FVector WorldPosition(
        PositionEnuMetres.Y * 100.0f,
        PositionEnuMetres.X * 100.0f,
        PositionEnuMetres.Z * 100.0f);
    InterceptMarker->SetRelativeLocation(WorldPosition);
    InterceptBeacon->SetRelativeLocation(WorldPosition + FVector(0, 0, 450.0f));
    InterceptBeacon->SetRelativeScale3D(FVector(0.10f, 0.10f, 5.0f));

    // Dotted column from ground level up to the predicted intercept point.
    // Discrete dashes read as an altitude scale and stay legible against
    // terrain, where a solid column or a large sphere does not.
    InterceptLadder->SetVisibility(true);
    InterceptLadder->ClearInstances();
    {
        const float TopZ = WorldPosition.Z;
        const float Step = 250.0f;                      // 2.5 m between dashes
        const int32 MaxDashes = 48;                     // bounded work per frame
        const float DashHalfHeight = 40.0f;             // 0.8 m dash
        int32 Placed = 0;
        for (float Z = Step; Z < TopZ && Placed < MaxDashes; Z += Step, ++Placed)
        {
            // Taper toward the top so the column reads as a direction, not a wall.
            const float Fraction = TopZ > KINDA_SMALL_NUMBER ? (Z / TopZ) : 0.0f;
            const float Width = FMath::Lerp(0.30f, 0.12f, Fraction);
            FTransform Dash;
            Dash.SetLocation(FVector(WorldPosition.X, WorldPosition.Y, Z));
            Dash.SetScale3D(FVector(Width, Width, DashHalfHeight / 50.0f));
            InterceptLadder->AddInstance(Dash);
        }
    }

    if (LadderMaterial != nullptr)
    {
        const FLinearColor LadderColor =
            Status.Equals(TEXT("INTERCEPTED"), ESearchCase::IgnoreCase)
                ? FLinearColor(0.15f, 1.0f, 0.42f)
                : (Status.Equals(TEXT("BREACH"), ESearchCase::IgnoreCase)
                    ? FLinearColor(1.0f, 0.12f, 0.08f)
                    : FLinearColor(1.0f, 0.72f, 0.10f));
        LadderMaterial->SetVectorParameterValue(TEXT("Color"), LadderColor);
    }

    if (InterceptMaterial != nullptr)
    {
        const FLinearColor Color = Status.Equals(TEXT("INTERCEPTED"), ESearchCase::IgnoreCase)
            ? FLinearColor(0.15f, 1.0f, 0.42f)
            : (Status.Equals(TEXT("BREACH"), ESearchCase::IgnoreCase)
                ? FLinearColor(1.0f, 0.12f, 0.08f)
                : FLinearColor(1.0f, 0.72f, 0.10f));
        InterceptMaterial->SetVectorParameterValue(TEXT("Color"), Color);
    }
}
