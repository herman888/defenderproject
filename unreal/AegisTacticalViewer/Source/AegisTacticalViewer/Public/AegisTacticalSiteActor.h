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

    /** Draws a display-only sightline to a track already validated by Python. */
    void SetSensorTrackPresentation(const FVector& PositionEnuMetres);

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

    /** Sparse dashes make a locked radar-to-track relation readable without a solid beam. */
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UInstancedStaticMeshComponent> SensorSightline;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> PerimeterMarker;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UTextRenderComponent> SiteLabel;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> InterceptMarker;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> InterceptBeacon;

    /** Dotted vertical column marking the predicted intercept point.
     *  Replaces a 3.2 m solid pulsing sphere, which occluded the engagement it
     *  was supposed to annotate and was hard to read against terrain. */
    UPROPERTY(VisibleAnywhere, Category = "Aegis|Site")
    TObjectPtr<UInstancedStaticMeshComponent> InterceptLadder;

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
    UPROPERTY()
    TObjectPtr<UMaterialInstanceDynamic> LadderMaterial;

    UPROPERTY()
    TObjectPtr<UMaterialInstanceDynamic> SightlineMaterial;

    void UpdateSensorSightline();
    float MarkerPulseSeconds = 0.0f;
    bool bMarkerVisible = false;
    bool bRadarLocked = false;
    bool bRadarFailed = false;
    bool bHasSensorTrack = false;
    FVector SensorTrackWorld = FVector::ZeroVector;
};
