#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalCameraActor.generated.h"

class UCameraComponent;
class USceneComponent;

/** Display-only camera that frames the latest authoritative tactical tracks. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalCameraActor : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalCameraActor();

    virtual void Tick(float DeltaSeconds) override;

    void SetTrackWorldPosition(const FString& TrackRole, const FVector& WorldPosition);

    /** Stops framing a track once the authoritative feed reports it absent. */
    void ClearTrack(const FString& TrackRole);

    /** C cycles chase, tactical overview, and terrain-follow presentation. */
    void CyclePresentationMode();
    FString GetPresentationModeLabel() const;

private:
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UCameraComponent> Camera;

    FVector IntruderPosition = FVector::ZeroVector;
    FVector InterceptorPosition = FVector::ZeroVector;
    bool bHasIntruder = false;
    bool bHasInterceptor = false;
    bool bClaimedPlayerView = false;
    int32 PresentationMode = 0;
};
