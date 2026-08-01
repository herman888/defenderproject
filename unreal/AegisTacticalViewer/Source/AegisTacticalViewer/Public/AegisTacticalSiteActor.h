#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalSiteActor.generated.h"

class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class USceneComponent;
class UTextRenderComponent;

/** A generic, display-only protected training site. It has no simulation authority. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalSiteActor : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalSiteActor();

    virtual void Tick(float DeltaSeconds) override;

    /** Shows the latest Python-computed intercept point; this is presentation-only. */
    void SetPredictedIntercept(
        const FVector& PositionEnuMetres, bool bVisible, const FString& Status);

    /** Visual radar state only; sensor truth remains in the telemetry feed. */
    void SetSensorPresentationState(bool bRadarLocked, bool bRadarFailed);

private:
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> SitePad;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> SensorTower;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> SensorDome;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> RadarAntenna;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> RadarPulse;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> PerimeterMarker;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UTextRenderComponent> SiteLabel;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> InterceptMarker;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> InterceptBeacon;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UInstancedStaticMeshComponent> CompoundBuildings;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UInstancedStaticMeshComponent> AccessRoad;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UInstancedStaticMeshComponent> PerimeterFence;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UInstancedStaticMeshComponent> Vegetation;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UInstancedStaticMeshComponent> RockScatter;

    UPROPERTY(Transient)
    TObjectPtr<UMaterialInstanceDynamic> InterceptMaterial;

    float MarkerPulseSeconds = 0.0f;
    bool bMarkerVisible = false;
    bool bRadarLocked = false;
    bool bRadarFailed = false;
};
