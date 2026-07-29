#include "AegisTacticalCameraActor.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/KismetMathLibrary.h"

AAegisTacticalCameraActor::AAegisTacticalCameraActor()
{
    PrimaryActorTick.bCanEverTick = true;
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    RootComponent = SceneRoot;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(SceneRoot);
    Camera->SetFieldOfView(58.0f);
}

void AAegisTacticalCameraActor::SetTrackWorldPosition(
    const FString& TrackRole, const FVector& WorldPosition)
{
    if (TrackRole == TEXT("intruder"))
    {
        IntruderPosition = WorldPosition;
        bHasIntruder = true;
    }
    else if (TrackRole == TEXT("interceptor"))
    {
        InterceptorPosition = WorldPosition;
        bHasInterceptor = true;
    }
}

void AAegisTacticalCameraActor::ClearTrack(const FString& TrackRole)
{
    if (TrackRole == TEXT("intruder"))
    {
        bHasIntruder = false;
    }
    else if (TrackRole == TEXT("interceptor"))
    {
        bHasInterceptor = false;
    }
}

void AAegisTacticalCameraActor::CyclePresentationMode()
{
    PresentationMode = (PresentationMode + 1) % 3;
}

FString AAegisTacticalCameraActor::GetPresentationModeLabel() const
{
    static const TCHAR* Labels[] = {TEXT("CHASE"), TEXT("TACTICAL"), TEXT("TERRAIN")};
    return Labels[PresentationMode];
}

void AAegisTacticalCameraActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);

    if (!bClaimedPlayerView)
    {
        if (APlayerController* PlayerController = GetWorld()->GetFirstPlayerController())
        {
            PlayerController->SetViewTarget(this);
            bClaimedPlayerView = true;
        }
    }
    if (!bHasIntruder)
    {
        return;
    }

    const FVector TrackFocus = bHasInterceptor
        ? (IntruderPosition + InterceptorPosition) * 0.5
        : IntruderPosition;
    const float Separation = bHasInterceptor
        ? FVector::Distance(IntruderPosition, InterceptorPosition)
        : 0.0f;
    // Aim partway down to the local ground plane so the local terrain remains
    // readable while the actor positions themselves remain authoritative.
    const FVector GroundFocus(TrackFocus.X, TrackFocus.Y, 0.0f);
    const float FocusFraction[] = {0.85f, 0.72f, 0.58f};
    const FVector Directions[] = {
        FVector(-0.78, -0.78, 0.34),
        FVector(-0.60, -0.60, 0.62),
        FVector(-0.82, -0.82, 0.42),
    };
    // Keep every camera presentation close enough for the track symbols,
    // labels, and trails to remain legible on a 1080p display. Separation is
    // real authoritative geometry, but should not push the display into a
    // near-orbital view during a long-range engagement.
    const float BaseDistances[] = {9000.0f, 15000.0f, 24000.0f};
    const FVector Focus = FMath::Lerp(GroundFocus, TrackFocus, FocusFraction[PresentationMode]);
    const float Distance = FMath::Clamp(BaseDistances[PresentationMode] + Separation * 0.25f,
        8000.0f, 50000.0f);
    const FVector Direction = Directions[PresentationMode].GetSafeNormal();
    const FVector DesiredLocation = Focus + Direction * Distance;
    const FRotator DesiredRotation = UKismetMathLibrary::FindLookAtRotation(
        DesiredLocation, Focus);

    if (!bHasFramedTrack)
    {
        SetActorLocation(DesiredLocation);
        SetActorRotation(DesiredRotation);
        bHasFramedTrack = true;
        return;
    }

    SetActorLocation(FMath::VInterpTo(
        GetActorLocation(), DesiredLocation, DeltaSeconds, 6.0f));
    SetActorRotation(FMath::RInterpTo(
        GetActorRotation(), DesiredRotation, DeltaSeconds, 6.0f));
}
