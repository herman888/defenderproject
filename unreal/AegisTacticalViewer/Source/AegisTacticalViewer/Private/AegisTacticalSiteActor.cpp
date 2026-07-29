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
    PrimaryActorTick.bCanEverTick = false;
    SitePad = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SitePad"));
    RootComponent = SitePad;
    SensorTower = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SensorTower"));
    SensorTower->SetupAttachment(SitePad);
    SensorDome = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SensorDome"));
    SensorDome->SetupAttachment(SitePad);
    PerimeterMarker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PerimeterMarker"));
    PerimeterMarker->SetupAttachment(SitePad);
    SiteLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("SiteLabel"));
    SiteLabel->SetupAttachment(SitePad);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMaterial(
        TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    if (Cylinder.Succeeded() && Sphere.Succeeded())
    {
        ConfigureStatic(SitePad, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.06f, 0.12f, 0.16f));
        ConfigureStatic(SensorTower, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.32f, 0.38f, 0.42f));
        ConfigureStatic(SensorDome, Sphere.Object, BasicMaterial.Object, FLinearColor(0.12f, 0.65f, 0.68f));
        ConfigureStatic(PerimeterMarker, Cylinder.Object, BasicMaterial.Object, FLinearColor(0.10f, 0.33f, 0.30f));
    }
    SitePad->SetRelativeScale3D(FVector(24.0f, 24.0f, 0.12f));
    SensorTower->SetRelativeLocation(FVector(0.0f, 0.0f, 1000.0f));
    SensorTower->SetRelativeScale3D(FVector(0.8f, 0.8f, 10.0f));
    SensorDome->SetRelativeLocation(FVector(0.0f, 0.0f, 2050.0f));
    SensorDome->SetRelativeScale3D(FVector(2.2f, 2.2f, 1.1f));
    PerimeterMarker->SetRelativeLocation(FVector(0.0f, 0.0f, 15.0f));
    PerimeterMarker->SetRelativeScale3D(FVector(52.0f, 52.0f, 0.03f));

    SiteLabel->SetText(FText::FromString(TEXT("PROTECTED TRAINING SITE")));
    SiteLabel->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
    SiteLabel->SetTextRenderColor(FColor(122, 224, 222));
    SiteLabel->SetWorldSize(150.0f);
    SiteLabel->SetRelativeLocation(FVector(0.0f, 0.0f, 2450.0f));
}
