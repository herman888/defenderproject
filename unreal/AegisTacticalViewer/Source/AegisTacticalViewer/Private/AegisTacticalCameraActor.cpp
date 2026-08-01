#include "AegisTacticalCameraActor.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/KismetMathLibrary.h"
#include "Engine/World.h"
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
        const bool bNewIntruder = !bHasIntruder;
        IntruderPosition = WorldPosition * 100.0f;
        IntruderVelocity = WorldVelocity;
        bHasIntruder = true;
        if (bNewIntruder)
        {
            bHasObserverAnchor = false;
            ObserverAnchorAgeSeconds = 0.0f;
        }
    }
    else if (Snapshot.Role.Equals(TEXT("interceptor"), ESearchCase::IgnoreCase))
    {
        const bool bNewDeployment = !bHasInterceptor;
        InterceptorPosition = WorldPosition * 100.0f;
        InterceptorVelocity = WorldVelocity;
        bHasInterceptor = true;
        if (bNewDeployment)
        {
            PresentationMode = 2;
            bHasFramedTrack = false;
            LastAutoCut = TEXT("INTERCEPTOR DEPLOYED");
        }
    }
}

void AAegisTacticalCameraActor::ClearTrack(const FString& TrackRole)
{
    if (TrackRole == TEXT("intruder"))
    {
        bHasIntruder = false;
        bHasObserverAnchor = false;
    }
    else if (TrackRole == TEXT("interceptor"))
    {
        bHasInterceptor = false;
    }
}

void AAegisTacticalCameraActor::CyclePresentationMode()
{
    PresentationMode = (PresentationMode + 1) % 6;
    // A Shahed-only ingress must never be presented as a chase shot: it makes
    // real world-space motion look stationary.  Chase becomes meaningful only
    // after the interceptor has been spawned from telemetry.
    if (!bHasInterceptor && PresentationMode == 2)
    {
        PresentationMode = 3;
    }
    LastAutoCut.Empty();
    bHasObserverAnchor = false;
}

FString AAegisTacticalCameraActor::GetPresentationModeLabel() const
{
    static const TCHAR* Labels[] = {
        TEXT("ENGAGEMENT"), TEXT("COMMAND"), TEXT("CHASE"),
        TEXT("TOP DOWN"), TEXT("ORBIT"), TEXT("SENSOR / EO")
    };
    return LastAutoCut.IsEmpty()
        ? Labels[PresentationMode]
        : FString::Printf(TEXT("%s / %s"), Labels[PresentationMode], *LastAutoCut);
}

void AAegisTacticalCameraActor::AddOrbitYaw(const float Value)
{
    if (PresentationMode == 4)
    {
        OrbitYawDegrees = FMath::UnwindDegrees(OrbitYawDegrees + Value * 2.4f);
    }
}

void AAegisTacticalCameraActor::AddOrbitPitch(const float Value)
{
    if (PresentationMode == 4)
    {
        OrbitPitchDegrees = FMath::Clamp(OrbitPitchDegrees + Value * 1.7f, 8.0f, 72.0f);
    }
}

void AAegisTacticalCameraActor::AddOrbitZoom(const float Value)
{
    if (PresentationMode == 4)
    {
        OrbitDistanceOffset = FMath::Clamp(OrbitDistanceOffset - Value * 1800.0f,
            -8500.0f, 18000.0f);
    }
}

void AAegisTacticalCameraActor::SetMissionPresentationState(
    const FTacticalTelemetryHealth& Health)
{
    if (!bHasMissionState)
    {
        bHasMissionState = true;
        bPreviousRadarLock = Health.bRadarLocked;
        PreviousMissionTimeSeconds = Health.LastMissionTimeSeconds;
        PreviousMissionStatus = Health.Status;
        return;
    }

    // Demo-repeat creates a fresh Python mission clock.  Without this reset,
    // the CHASE cut selected for the previous interceptor persisted into the
    // next Shahed-only ingress and visually pinned the target again.
    if (PreviousMissionTimeSeconds >= 5.0 && Health.LastMissionTimeSeconds <= 1.0)
    {
        PresentationMode = 0;
        bHasFramedTrack = false;
        bHasSmoothedFocus = false;
        bHasObserverAnchor = false;
        LastAutoCut = TEXT("INBOUND RANGE OBSERVER");
    }

    // These cuts react only to already-validated telemetry. They never alter
    // tracks, sensor state, or the Python mission.
    if (!bPreviousRadarLock && Health.bRadarLocked)
    {
        PresentationMode = 0;
        bHasFramedTrack = false;
        bHasObserverAnchor = false;
        LastAutoCut = TEXT("RADAR ACQUIRED");
    }
    if (!PreviousMissionStatus.Equals(TEXT("INTERCEPTED"), ESearchCase::IgnoreCase)
        && Health.Status.Equals(TEXT("INTERCEPTED"), ESearchCase::IgnoreCase))
    {
        PresentationMode = 4;
        bHasFramedTrack = false;
        bHasObserverAnchor = false;
        LastAutoCut = TEXT("INTERCEPT");
    }
    bPreviousRadarLock = Health.bRadarLocked;
    PreviousMissionTimeSeconds = Health.LastMissionTimeSeconds;
    PreviousMissionStatus = Health.Status;
}

void AAegisTacticalCameraActor::Tick(float DeltaSeconds)
{
    if (HitStopTimeRemaining > 0.0f)
    {
        CustomTimeDilation = HitStopTimeDilation;
        HitStopTimeRemaining -= GetWorld() ? GetWorld()->GetDeltaSeconds() : (DeltaSeconds / HitStopTimeDilation);
    }
    else
    {
        CustomTimeDilation = 1.0f;
    }

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
    const FVector AverageVelocity = bHasInterceptor
        ? (IntruderVelocity + InterceptorVelocity) * 0.5f
        : IntruderVelocity;
    // Look slightly ahead of the authoritative tracks. This changes framing,
    // never vehicle state, and gives fast motion room to enter the shot.
    const FVector LeadFocus = TrackFocus + AverageVelocity * 100.0f * 0.28f;
    const float Separation = bHasInterceptor
        ? FVector::Distance(IntruderPosition, InterceptorPosition)
        : 0.0f;

    CheckInterceptProximity(Separation);

    const FVector GroundFocus(LeadFocus.X, LeadFocus.Y, 0.0f);
    FVector Focus = PresentationMode == 1
        ? FMath::Lerp(GroundFocus, LeadFocus, 0.48f) : LeadFocus;
    FVector LookAtFocus = Focus;
    if (!bHasInterceptor && PresentationMode == 0)
    {
        // A real range-observer shot: select a single world-space point ahead
        // of the confirmed inbound path and do not follow the intruder.  The
        // previous soft-follow still made an aircraft at 50 m/s appear pinned
        // to the terrain.  We cut to the close engagement framing only once
        // the interceptor exists.
        if (!bHasObserverAnchor)
        {
            ObserverAnchor = LeadFocus + AverageVelocity * 100.0f * 4.5f;
            ObserverAnchorAgeSeconds = 0.0f;
            bHasObserverAnchor = true;
        }
        Focus = ObserverAnchor;
        LookAtFocus = ObserverAnchor;
    }
    // The earlier 220 m default read as a terrain flyover and made aircraft
    // silhouettes too small. Start with a close tactical-replay frame, then
    // expand only enough to keep both tracks visible during an engagement.
    // The pre-launch observer is deliberately a high, fixed range overlook.
    // Keeping it above the terrain avoids World Partition/landscape edges
    // being mistaken for a camera-obstruction and preserves the aircraft's
    // world-space transit through the frame.
    FVector Direction = bHasInterceptor
        ? FVector(-0.70f, -0.70f, 0.34f)
        : FVector(-0.38f, -0.38f, 0.84f).GetSafeNormal();
    float BaseDistance = bHasInterceptor ? 7000.0f : 40000.0f;
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
        const float Angle = FMath::DegreesToRadians(OrbitYawDegrees);
        const float Elevation = FMath::DegreesToRadians(OrbitPitchDegrees);
        Direction = FVector(
            FMath::Cos(Angle) * FMath::Cos(Elevation),
            FMath::Sin(Angle) * FMath::Cos(Elevation),
            FMath::Sin(Elevation)).GetSafeNormal();
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
        Camera->SetFieldOfView(bHasInterceptor
            ? FMath::Clamp(52.0f + Separation / 6000.0f, 52.0f, 64.0f)
            : 70.0f);
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
        : FMath::Clamp(BaseDistance + Separation * 0.35f
            + (PresentationMode == 4 ? OrbitDistanceOffset : 0.0f), 5500.0f, 50000.0f);
    FVector DesiredLocation = PresentationMode == 5
        ? FVector(-1500.0f, -1500.0f, 1200.0f)
        : Focus + Direction * Distance;
    const bool bFixedRangeObserver = !bHasInterceptor && PresentationMode == 0;
    if (PresentationMode != 5 && !bFixedRangeObserver && GetWorld() != nullptr)
    {
        FHitResult TerrainHit;
        FCollisionQueryParams TraceParams(SCENE_QUERY_STAT(AegisCameraClearance), false, this);
        if (GetWorld()->LineTraceSingleByChannel(
            TerrainHit, Focus, DesiredLocation, ECC_Visibility, TraceParams))
        {
            // Keep the camera out of terrain and authored compound geometry.
            DesiredLocation = TerrainHit.Location + TerrainHit.ImpactNormal * 450.0f;
        }
        DesiredLocation.Z = FMath::Max(DesiredLocation.Z, 350.0f);
    }
    else if (bFixedRangeObserver)
    {
        // No line trace here: this is an intentionally exterior shot above
        // the entire approach corridor, never an attempt to hug the terrain.
        DesiredLocation.Z = FMath::Max(DesiredLocation.Z, Focus.Z + 18000.0f);
    }
    const FRotator DesiredRotation = UKismetMathLibrary::FindLookAtRotation(
        DesiredLocation, LookAtFocus);

    if (!bHasFramedTrack)
    {
        SetActorLocation(DesiredLocation);
        SetActorRotation(DesiredRotation);
        bHasFramedTrack = true;
        return;
    }

    const float LocationFollowSpeed = !bHasInterceptor && PresentationMode == 0
        ? 0.01f : 6.0f;
    SetActorLocation(FMath::VInterpTo(
        GetActorLocation(), DesiredLocation, DeltaSeconds, LocationFollowSpeed));
    SetActorRotation(FMath::RInterpTo(
        GetActorRotation(), DesiredRotation, DeltaSeconds, 6.0f));
}

void AAegisTacticalCameraActor::TriggerHitStop(float Duration)
{
    HitStopTimeRemaining = Duration;
}

void AAegisTacticalCameraActor::CheckInterceptProximity(float Separation)
{
    if (bHasInterceptor && Separation > 0.0f && Separation < 1500.0f && HitStopTimeRemaining <= 0.0f)
    {
        TriggerHitStop();
    }
}
