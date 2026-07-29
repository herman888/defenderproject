#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalSiteActor.generated.h"

class UStaticMeshComponent;
class UTextRenderComponent;

/** A generic, display-only protected training site. It has no simulation authority. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalSiteActor : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalSiteActor();

    virtual void Tick(float DeltaSeconds) override;

private:
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> SitePad;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> SensorTower;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> SensorDome;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> RadarAntenna;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> PerimeterMarker;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UTextRenderComponent> SiteLabel;
};
