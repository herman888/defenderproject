#include "AegisTacticalCameraActor.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/KismetMathLibrary.h"
#include "TacticalTypes.h"

AAegisTacticalCameraActor::AAegisTacticalCameraActor()
{
    PrimaryActorTick.bCanEverTick = true;
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    RootComponent = SceneRoot;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(SceneRoot);
    Camera->SetFieldOfView(58.0f);
}

void AAegisTacticalCameraActor::SetTrackSnapshot(const FTacticalTrackSnapshot& Snapshot)
{
    const FVector WorldPosition(Snapshot.PositionEnuMetres.Y, Snapshot.PositionEnuMetres.X,
        Snapshot.PositionEnuMetres.Z);
    const FVector WorldVelocity(Snapshot.VelocityEnuMetresPerSecond.Y,
        Snapshot.VelocityEnuMetresPerSecond.X, Snapshot.VelocityEnuMetresPerSecond.Z);
    if (Snapshot.Role.Equals(TEXT("intruder"), ESearchCase::IgnoreCase))
    {
        IntruderPosition = WorldPosition * 100.0f;
        IntruderVelocity = WorldVelocity;
        bHasIntruder = true;
    }
    else if (Snapshot.Role.Equals(TEXT("interceptor"), ESearchCase::IgnoreCase))
    {
        InterceptorPosition = WorldPosition * 100.0f;
        InterceptorVelocity = WorldVelocity;
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
    PresentationMode = (PresentationMode + 1) % 6;
}

FString AAegisTacticalCameraActor::GetPresentationModeLabel() const
{
    static const TCHAR* Labels[] = {
        TEXT("ENGAGEMENT"), TEXT("COMMAND"), TEXT("CHASE"),
        TEXT("TOP DOWN"), TEXT("ORBIT"), TEXT("SENSOR / EO")
    };
    return Labels[PresentationMode];
}

void AAegisTacticalCameraActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    PresentationSeconds += DeltaSeconds;

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

    FVector TrackFocus = bHasInterceptor
        ? (IntruderPosition + InterceptorPosition) * 0.5
        : IntruderPosition;
    const FVector AverageVelocity = bHasInterceptor
        ? (IntruderVelocity + InterceptorVelocity) * 0.5f
        : IntruderVelocity;
    // Look slightly ahead of the authoritative tracks. This changes framing,
    // never vehicle state, and gives fast motion room to enter the shot.
    TrackFocus += AverageVelocity * 100.0f * 0.28f;
    const float Separation = bHasInterceptor
        ? FVector::Distance(IntruderPosition, InterceptorPosition)
        : 0.0f;
    const FVector GroundFocus(TrackFocus.X, TrackFocus.Y, 0.0f);
    FVector Focus = PresentationMode == 1
        ? FMath::Lerp(GroundFocus, TrackFocus, 0.48f) : TrackFocus;
    // The earlier 220 m default read as a terrain flyover and made aircraft
    // silhouettes too small. Start with a close tactical-replay frame, then
    // expand only enough to keep both tracks visible during an engagement.
    FVector Direction(-0.70f, -0.70f, 0.34f);
    float BaseDistance = 7000.0f;
    if (PresentationMode == 1)
    {
        Direction = FVector(-0.22f, -0.22f, 0.95f);
        BaseDistance = 32000.0f;
        Camera->SetFieldOfView(66.0f);
    }
    else if (PresentationMode == 2)
    {
        const FVector ChaseVelocity = (bHasInterceptor ? InterceptorVelocity : IntruderVelocity).GetSafeNormal();
        Focus = (
            bHasInterceptor ? InterceptorPosition : IntruderPosition
        ) + (bHasInterceptor ? InterceptorVelocity : IntruderVelocity) * 100.0f * 0.42f;
        Direction = (ChaseVelocity.IsNearlyZero() ? FVector(-1.0f, -1.0f, 0.35f) : -ChaseVelocity + FVector(0.0f, 0.0f, 0.28f)).GetSafeNormal();
        BaseDistance = 7000.0f;
        Camera->SetFieldOfView(62.0f);
    }
    else if (PresentationMode == 3)
    {
        Direction = FVector::UpVector;
        BaseDistance = 42000.0f;
        Camera->SetFieldOfView(52.0f);
    }
    else if (PresentationMode == 4)
    {
        const float Angle = PresentationSeconds * 0.16f;
        Direction = FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.46f).GetSafeNormal();
        BaseDistance = 16000.0f;
        Camera->SetFieldOfView(65.0f);
    }
    else if (PresentationMode == 5)
    {
        // Simulated optical presentation from the radar compound. This is a
        // camera view only; sensor detections still come from Python telemetry.
        Focus = IntruderPosition;
        Direction = FVector::ZeroVector;
        BaseDistance = 0.0f;
        Camera->SetFieldOfView(24.0f);
    }
    else
    {
        Camera->SetFieldOfView(FMath::Clamp(
            52.0f + Separation / 6000.0f, 52.0f, 64.0f));
    }
    if (!bHasSmoothedFocus)
    {
        SmoothedFocus = Focus;
        bHasSmoothedFocus = true;
    }
    else if (PresentationMode != 5)
    {
        SmoothedFocus = FMath::VInterpTo(
            SmoothedFocus, Focus, DeltaSeconds, 8.0f);
        Focus = SmoothedFocus;
    }
    const float Distance = PresentationMode == 5
        ? 0.0f
        : FMath::Clamp(BaseDistance + Separation * 0.35f, 5500.0f, 50000.0f);
    const FVector DesiredLocation = PresentationMode == 5
        ? FVector(-1500.0f, -1500.0f, 1200.0f)
        : Focus + Direction * Distance;
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
