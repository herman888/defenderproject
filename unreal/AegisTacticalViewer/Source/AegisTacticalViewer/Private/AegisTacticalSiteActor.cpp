#include "AegisTacticalSiteActor.h"

#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
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
}

AAegisTacticalSiteActor::AAegisTacticalSiteActor()
{
    // The rotating antenna is visual context only. Python remains the sole
    // authority for radar sensing and all mission state.
    PrimaryActorTick.bCanEverTick = true;
    SitePad = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SitePad"));
    RootComponent = SitePad;
    SensorTower = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SensorTower"));
    SensorTower->SetupAttachment(SitePad);
    SensorDome = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SensorDome"));
    SensorDome->SetupAttachment(SitePad);
    RadarAntenna = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RadarAntenna"));
    RadarAntenna->SetupAttachment(SitePad);
    PerimeterMarker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PerimeterMarker"));
    PerimeterMarker->SetupAttachment(SitePad);
    SiteLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("SiteLabel"));
    SiteLabel->SetupAttachment(SitePad);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMaterial(
        TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    if (Cylinder.Succeeded() && Sphere.Succeeded())
    {
        ConfigureStatic(SitePad, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.06f, 0.12f, 0.16f));
        ConfigureStatic(SensorTower, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.32f, 0.38f, 0.42f));
        ConfigureStatic(SensorDome, Sphere.Object, BasicMaterial.Object, FLinearColor(0.12f, 0.65f, 0.68f));
        ConfigureStatic(RadarAntenna, Cube.Object, BasicMaterial.Object, FLinearColor(0.14f, 0.76f, 0.78f));
    }
    SitePad->SetRelativeScale3D(FVector(24.0f, 24.0f, 0.12f));
    // RadarNode is at local ENU (0, 0, 10 m).  Keep the visual antenna at
    // that same height: Unreal uses centimetres.
    SensorTower->SetRelativeLocation(FVector(0.0f, 0.0f, 500.0f));
    SensorTower->SetRelativeScale3D(FVector(0.8f, 0.8f, 5.0f));
    SensorDome->SetRelativeLocation(FVector(0.0f, 0.0f, 1025.0f));
    SensorDome->SetRelativeScale3D(FVector(1.35f, 1.35f, 0.7f));
    RadarAntenna->SetRelativeLocation(FVector(0.0f, 0.0f, 1110.0f));
    RadarAntenna->SetRelativeScale3D(FVector(4.0f, 0.18f, 0.12f));

    // This was an opaque 104 m green disc, which looked like a pool on the
    // terrain. A radius is a tactical concept, not a solid physical object.
    PerimeterMarker->SetVisibility(false);
    PerimeterMarker->SetHiddenInGame(true);

    SiteLabel->SetText(FText::FromString(TEXT("PROTECTED TRAINING SITE")));
    SiteLabel->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
    SiteLabel->SetTextRenderColor(FColor(122, 224, 222));
    SiteLabel->SetWorldSize(150.0f);
    SiteLabel->SetRelativeLocation(FVector(0.0f, 0.0f, 1450.0f));
}

void AAegisTacticalSiteActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (RadarAntenna != nullptr)
    {
        RadarAntenna->AddLocalRotation(FRotator(0.0f, 42.0f * DeltaSeconds, 0.0f));
    }
}
