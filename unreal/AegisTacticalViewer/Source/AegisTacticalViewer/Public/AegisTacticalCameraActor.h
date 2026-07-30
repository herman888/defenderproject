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
    bool bHasIntruder = false;
    bool bHasInterceptor = false;
    bool bClaimedPlayerView = false;
    bool bHasFramedTrack = false;
    bool bHasSmoothedFocus = false;
    int32 PresentationMode = 0;
    float PresentationSeconds = 0.0f;
};
