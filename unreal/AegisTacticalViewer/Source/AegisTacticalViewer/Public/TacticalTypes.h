#pragma once

#include "CoreMinimal.h"

/** One validated, display-only track from aegis.unreal-bridge.v1. */
struct FTacticalTrackSnapshot
{
    FString Id;
    FString Role;
    FString AssetId;
    FString Type;
    FVector PositionEnuMetres = FVector::ZeroVector;
    FVector VelocityEnuMetresPerSecond = FVector::ZeroVector;
    FQuat OrientationEnu = FQuat::Identity;
    double HeadingDegrees = 0.0;
};

/** Health exposed to the HUD; presentation state never feeds Python. */
struct FTacticalTelemetryHealth
{
    int64 ReceivedPackets = 0;
    int64 ForwardedPackets = 0;
    int64 RejectedPackets = 0;
    int64 DroppedPackets = 0;
    int64 LastSequence = -1;
    double LastMissionTimeSeconds = -1.0;
    float LastReceiveWorldSeconds = -BIG_NUMBER;
    FString Status = TEXT("WAITING");
    FString Site = TEXT("LOCAL");

    // The local Python simulator intentionally favours deterministic physics
    // over a fixed display cadence on modest GPUs. Five seconds still surfaces
    // a genuinely disconnected loopback feed without falsely alarming during
    // an otherwise healthy, slower simulation frame.
    bool IsStale(float WorldSeconds, float TimeoutSeconds = 5.0f) const
    {
        return LastReceiveWorldSeconds < 0.0f
            || WorldSeconds - LastReceiveWorldSeconds > TimeoutSeconds;
    }

    float PacketAgeSeconds(float WorldSeconds) const
    {
        return LastReceiveWorldSeconds < 0.0f
            ? BIG_NUMBER
            : FMath::Max(0.0f, WorldSeconds - LastReceiveWorldSeconds);
    }
};
