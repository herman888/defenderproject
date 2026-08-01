#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalCameraActor.generated.h"

class UCameraComponent;
struct FTacticalTrackSnapshot;
class USceneComponent;

/** Display-only camera that frames the latest authoritative tactical tracks. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalCameraActor : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalCameraActor();

    virtual void Tick(float DeltaSeconds) override;

    void SetTrackSnapshot(const FTacticalTrackSnapshot& Snapshot);

    /** Stops framing a track once the authoritative feed reports it absent. */
    void ClearTrack(const FString& TrackRole);

    /** C cycles engagement, command, chase, top-down, orbit, and EO presentation. */
    void CyclePresentationMode();
    FString GetPresentationModeLabel() const;

    /** Manual orbit inputs only affect the orbit presentation mode. */

    void AddOrbitYaw(float Value);
    void AddOrbitPitch(float Value);
    void AddOrbitZoom(float Value);

    /** Receives display state only, for non-authoritative cinematic camera beats. */
    void SetMissionPresentationState(const struct FTacticalTelemetryHealth& Health);

private:
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UCameraComponent> Camera;

    FVector IntruderPosition = FVector::ZeroVector;
    FVector InterceptorPosition = FVector::ZeroVector;
    FVector IntruderVelocity = FVector::ForwardVector;
    FVector InterceptorVelocity = FVector::ForwardVector;
    FVector SmoothedFocus = FVector::ZeroVector;
    // The pre-intercept observer deliberately retains a world-space anchor for
    // a short beat.  A camera glued to the intruder makes real telemetry
    // motion look stationary against the terrain.
    FVector ObserverAnchor = FVector::ZeroVector;
    bool bHasIntruder = false;
    bool bHasInterceptor = false;
    bool bClaimedPlayerView = false;
    bool bHasFramedTrack = false;
    bool bHasSmoothedFocus = false;
    bool bHasObserverAnchor = false;
    float ObserverAnchorAgeSeconds = 0.0f;
    int32 PresentationMode = 0;
    float PresentationSeconds = 0.0f;
    float OrbitYawDegrees = 0.0f;
    float OrbitPitchDegrees = 27.0f;
    float OrbitDistanceOffset = 0.0f;
    bool bPreviousRadarLock = false;
    bool bHasMissionState = false;
    double PreviousMissionTimeSeconds = -1.0;
    FString PreviousMissionStatus;
    FString LastAutoCut;
};
