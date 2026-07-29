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
    PresentationMode = (PresentationMode + 1) % 4;
}

FString AAegisTacticalCameraActor::GetPresentationModeLabel() const
{
    static const TCHAR* Labels[] = {TEXT("ENGAGEMENT"), TEXT("COMMAND"), TEXT("CHASE"), TEXT("ORBIT")};
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

    const FVector TrackFocus = bHasInterceptor
        ? (IntruderPosition + InterceptorPosition) * 0.5
        : IntruderPosition;
    const float Separation = bHasInterceptor
        ? FVector::Distance(IntruderPosition, InterceptorPosition)
        : 0.0f;
    const FVector GroundFocus(TrackFocus.X, TrackFocus.Y, 0.0f);
    const FVector Focus = PresentationMode == 1
        ? FMath::Lerp(GroundFocus, TrackFocus, 0.48f) : TrackFocus;
    FVector Direction(-0.70f, -0.70f, 0.34f);
    float BaseDistance = 22000.0f;
    if (PresentationMode == 1)
    {
        Direction = FVector(-0.22f, -0.22f, 0.95f);
        BaseDistance = 45000.0f;
        Camera->SetFieldOfView(66.0f);
    }
    else if (PresentationMode == 2)
    {
        const FVector ChaseVelocity = (bHasInterceptor ? InterceptorVelocity : IntruderVelocity).GetSafeNormal();
        Direction = (ChaseVelocity.IsNearlyZero() ? FVector(-1.0f, -1.0f, 0.35f) : -ChaseVelocity + FVector(0.0f, 0.0f, 0.28f)).GetSafeNormal();
        BaseDistance = 14500.0f;
        Camera->SetFieldOfView(62.0f);
    }
    else if (PresentationMode == 3)
    {
        const float Angle = PresentationSeconds * 0.16f;
        Direction = FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.46f).GetSafeNormal();
        BaseDistance = 28000.0f;
        Camera->SetFieldOfView(65.0f);
    }
    else
    {
        Camera->SetFieldOfView(60.0f);
    }
    const float Distance = FMath::Clamp(BaseDistance + Separation * 0.45f, 12000.0f, 85000.0f);
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
