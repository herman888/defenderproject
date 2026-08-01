#include "AegisTacticalHUD.h"

#include "AegisTacticalCameraActor.h"
#include "AegisTacticalPlayerController.h"
#include "AegisTacticalTelemetryManager.h"
#include "AegisTacticalTrackActor.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Kismet/GameplayStatics.h"
#include "TacticalTelemetryComponent.h"

namespace
{
FLinearColor StatusColor(const FString& Status)
{
    if (Status.Equals(TEXT("BREACH"), ESearchCase::IgnoreCase))
    {
        return FLinearColor(1.0f, 0.18f, 0.16f, 1.0f);
    }
    if (Status.Equals(TEXT("INTERCEPTED"), ESearchCase::IgnoreCase))
    {
        return FLinearColor(0.22f, 0.95f, 0.48f, 1.0f);
    }
    if (Status.Equals(TEXT("TRACKING"), ESearchCase::IgnoreCase))
    {
        return FLinearColor(1.0f, 0.73f, 0.18f, 1.0f);
    }
    return FLinearColor(0.48f, 0.82f, 0.94f, 1.0f);
}

FString SensorState(const bool bFailure, const bool bLocked)
{
    return bFailure ? TEXT("FAILED") : (bLocked ? TEXT("LOCK") : TEXT("SEARCH"));
}
}

void AAegisTacticalHUD::UpdateHistory(
    const FTacticalTelemetryHealth& Health,
    const FTacticalTrackSnapshot* Intruder,
    const FTacticalTrackSnapshot* Interceptor)
{
    if (Intruder == nullptr || Health.LastMissionTimeSeconds < 0.0)
    {
        return;
    }
    if (LastHistoryMissionTime >= 0.0
        && Health.LastMissionTimeSeconds < LastHistoryMissionTime)
    {
        IntruderSpeedHistory.Reset();
        InterceptorSpeedHistory.Reset();
        AltitudeHistory.Reset();
        RangeHistory.Reset();
        LastHistoryMissionTime = -1.0;
    }
    if (Health.LastMissionTimeSeconds <= LastHistoryMissionTime + 0.18)
    {
        return;
    }
    LastHistoryMissionTime = Health.LastMissionTimeSeconds;
    IntruderSpeedHistory.Add(Intruder->VelocityEnuMetresPerSecond.Length());
    InterceptorSpeedHistory.Add(
        Interceptor != nullptr ? Interceptor->VelocityEnuMetresPerSecond.Length() : 0.0f);
    AltitudeHistory.Add(Intruder->PositionEnuMetres.Z);
    RangeHistory.Add(Intruder->PositionEnuMetres.Length());
    constexpr int32 MaxHistorySamples = 180;
    while (IntruderSpeedHistory.Num() > MaxHistorySamples)
    {
        IntruderSpeedHistory.RemoveAt(0);
        InterceptorSpeedHistory.RemoveAt(0);
        AltitudeHistory.RemoveAt(0);
        RangeHistory.RemoveAt(0);
    }
}

void AAegisTacticalHUD::DrawHUD()
{
    Super::DrawHUD();
    if (Canvas == nullptr)
    {
        return;
    }

    UFont* Font = GEngine != nullptr ? GEngine->GetSmallFont() : nullptr;
    const float ScreenW = Canvas->SizeX;
    const float ScreenH = Canvas->SizeY;
    const FLinearColor Panel(0.005f, 0.018f, 0.035f, 0.82f);
    const FLinearColor HeaderColor(0.70f, 0.88f, 1.0f, 1.0f);
    const FLinearColor Body(0.82f, 0.86f, 0.90f, 1.0f);
    const FLinearColor Muted(0.57f, 0.63f, 0.68f, 1.0f);
    const FLinearColor Cyan(0.14f, 0.86f, 0.82f, 1.0f);
    const FLinearColor Orange(1.0f, 0.56f, 0.30f, 1.0f);
    const FLinearColor Blue(0.28f, 0.72f, 1.0f, 1.0f);

    const AAegisTacticalTelemetryManager* Manager = Cast<AAegisTacticalTelemetryManager>(
        UGameplayStatics::GetActorOfClass(
            GetWorld(), AAegisTacticalTelemetryManager::StaticClass()));
    const UTacticalTelemetryComponent* Telemetry =
        Manager != nullptr ? Manager->Telemetry : nullptr;
    if (Telemetry == nullptr)
    {
        DrawText(TEXT("LINK: INITIALIZING"), FLinearColor::Yellow,
            28.0f, 28.0f, Font, 1.1f);
        return;
    }

    const FTacticalTelemetryHealth& Health = Telemetry->GetHealth();
    FTacticalTrackSnapshot Intruder;
    FTacticalTrackSnapshot Interceptor;
    const bool bHasIntruder =
        Telemetry->GetLatestSnapshot(TEXT("intruder"), Intruder);
    const bool bHasInterceptor =
        Telemetry->GetLatestSnapshot(TEXT("interceptor"), Interceptor);
    const auto DrawTrackBox = [this, ScreenW, ScreenH, Font](
        const FTacticalTrackSnapshot& Track, const FString& Name,
        const FLinearColor& Color)
    {
        APlayerController* Controller = GetOwningPlayerController();
        if (Controller == nullptr)
        {
            return;
        }
        const FVector WorldPosition =
            AAegisTacticalTrackActor::EnuToUnrealWorld(Track.PositionEnuMetres);
        FVector2D ScreenPosition(ForceInitToZero);
        const bool bProjected = Controller->ProjectWorldLocationToScreen(
            WorldPosition, ScreenPosition, true);
        const FVector CameraLocation = Controller->PlayerCameraManager != nullptr
            ? Controller->PlayerCameraManager->GetCameraLocation() : FVector::ZeroVector;
        const FVector CameraForward = Controller->PlayerCameraManager != nullptr
            ? Controller->PlayerCameraManager->GetCameraRotation().Vector() : FVector::ForwardVector;
        const bool bInFront = FVector::DotProduct(WorldPosition - CameraLocation, CameraForward) > 0.0f;
        const bool bOnScreen = bProjected && bInFront
            && ScreenPosition.X > 28.0f && ScreenPosition.X < ScreenW - 28.0f
            && ScreenPosition.Y > 28.0f && ScreenPosition.Y < ScreenH - 28.0f;
        if (bOnScreen)
        {
            constexpr float BoxSize = 30.0f;
            DrawLine(ScreenPosition.X - BoxSize, ScreenPosition.Y - BoxSize,
                ScreenPosition.X + BoxSize, ScreenPosition.Y - BoxSize, Color, 1.7f);
            DrawLine(ScreenPosition.X + BoxSize, ScreenPosition.Y - BoxSize,
                ScreenPosition.X + BoxSize, ScreenPosition.Y + BoxSize, Color, 1.7f);
            DrawLine(ScreenPosition.X + BoxSize, ScreenPosition.Y + BoxSize,
                ScreenPosition.X - BoxSize, ScreenPosition.Y + BoxSize, Color, 1.7f);
            DrawLine(ScreenPosition.X - BoxSize, ScreenPosition.Y + BoxSize,
                ScreenPosition.X - BoxSize, ScreenPosition.Y - BoxSize, Color, 1.7f);
            DrawText(FString::Printf(TEXT("%s  %.0f m"), *Name,
                Track.PositionEnuMetres.Z), Color, ScreenPosition.X + 36.0f,
                ScreenPosition.Y - 25.0f, Font, 0.68f);
            return;
        }
        FVector2D Direction = ScreenPosition - FVector2D(ScreenW * 0.5f, ScreenH * 0.5f);
        if (!bInFront)
        {
            Direction *= -1.0f;
        }
        if (Direction.IsNearlyZero())
        {
            Direction = FVector2D(0.0f, -1.0f);
        }
        Direction.Normalize();
        const FVector2D Center(ScreenW * 0.5f, ScreenH * 0.5f);
        const FVector2D Arrow = Center + Direction * FMath::Min(ScreenW, ScreenH) * 0.40f;
        const FVector2D Side(-Direction.Y, Direction.X);
        DrawLine(Arrow.X, Arrow.Y, Arrow.X - Direction.X * 18.0f + Side.X * 9.0f,
            Arrow.Y - Direction.Y * 18.0f + Side.Y * 9.0f, Color, 2.0f);
        DrawLine(Arrow.X, Arrow.Y, Arrow.X - Direction.X * 18.0f - Side.X * 9.0f,
            Arrow.Y - Direction.Y * 18.0f - Side.Y * 9.0f, Color, 2.0f);
        DrawText(Name, Color, Arrow.X + 8.0f, Arrow.Y + 8.0f, Font, 0.60f);
    };
    if (bHasIntruder)
    {
        DrawTrackBox(Intruder, TEXT("THREAT"), Orange);
    }
    if (bHasInterceptor)
    {
        DrawTrackBox(Interceptor, TEXT("INTERCEPTOR"), Blue);
    }
    if (bCleanCinematicMode)
    {
        DrawText(TEXT("CLEAN CINEMATIC  [H] FULL TACTICAL"),
            FLinearColor(0.75f, 0.84f, 0.88f, 0.72f), 24.0f,
            ScreenH - 30.0f, Font, 0.66f);
        return;
    }

    DrawRect(Panel, 16.0f, 14.0f, 520.0f, 210.0f);
    DrawRect(Cyan, 16.0f, 14.0f, 520.0f, 2.0f);
    DrawText(TEXT("AEGIS TACTICAL VIEWER"), HeaderColor, 28.0f, 24.0f, Font, 1.35f);
    DrawText(TEXT("VALIDATED DISPLAY CLIENT  |  LOOPBACK UDP :8788"),
        Muted, 28.0f, 50.0f, Font, 0.82f);
    const AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(
        GetOwningPlayerController() != nullptr
            ? GetOwningPlayerController()->GetViewTarget() : nullptr);
    DrawText(FString::Printf(TEXT("VIEW: %s  |  [C] CYCLE 6 TACTICAL CAMERAS"),
        Camera != nullptr ? *Camera->GetPresentationModeLabel() : TEXT("INITIALIZING")),
        Muted, 28.0f, 68.0f, Font, 0.76f);

    const float WorldSeconds = GetWorld() != nullptr ? GetWorld()->GetTimeSeconds() : 0.0f;
    const bool bStale = Health.IsStale(WorldSeconds);
    const FLinearColor LinkColor = Health.ReceivedPackets == 0
        ? FLinearColor::Yellow
        : (bStale ? FLinearColor(1.0f, 0.55f, 0.10f, 1.0f)
                  : FLinearColor(0.20f, 0.95f, 0.48f, 1.0f));
    const FString Link = Health.ReceivedPackets == 0
        ? TEXT("LINK: WAITING FOR LOCAL TELEMETRY")
        : FString::Printf(TEXT("LINK: %s  |  AGE %.2fs  |  LOSS %lld  |  REJECTED %lld"),
            bStale ? TEXT("STALE") : TEXT("LIVE"),
            Health.PacketAgeSeconds(WorldSeconds),
            Health.DroppedPackets, Health.RejectedPackets);
    DrawText(Link, LinkColor, 28.0f, 98.0f, Font, 1.0f);
    DrawText(FString::Printf(TEXT("T+ %.1fs  |  SEQ %lld  |  STATE %s"),
        Health.LastMissionTimeSeconds, Health.LastSequence, *Health.Status),
        Body, 28.0f, 122.0f, Font, 0.90f);
    DrawText(FString::Printf(TEXT("SCENARIO  %s / %s / %s PAD"),
        *Health.ScenarioIntruder.ToUpper(),
        *Health.ScenarioPattern.ToUpper(),
        *Health.ScenarioPad.ToUpper()),
        FLinearColor(0.78f, 0.82f, 0.86f, 1.0f), 28.0f, 144.0f, Font, 0.80f);
    DrawText(FString::Printf(TEXT("ENV  %s  |  VIS %.1f km  |  WIND %.1f m/s"),
        *Health.EnvironmentName.ToUpper(),
        Health.VisibilityMetres / 1000.0,
        Health.WindEnuMetresPerSecond.Length()),
        Muted, 28.0f, 164.0f, Font, 0.78f);
    DrawText(FString::Printf(TEXT("%s  |  SIMULATED TRAINING ENVIRONMENT"),
        Health.bRecording ? TEXT("RECORDING JSONL + ACMI") : TEXT("LIVE ONLY")),
        Cyan, 28.0f, 184.0f, Font, 0.72f);

    UpdateHistory(
        Health,
        bHasIntruder ? &Intruder : nullptr,
        bHasInterceptor ? &Interceptor : nullptr);

    const float PanelX = ScreenW - 396.0f;
    DrawRect(Panel, PanelX, 14.0f, 380.0f, 372.0f);
    DrawRect(StatusColor(Health.Status), PanelX, 14.0f, 380.0f, 2.0f);
    DrawText(TEXT("LIVE TACTICAL DATA"), HeaderColor,
        PanelX + 16.0f, 24.0f, Font, 1.05f);
    DrawText(FString::Printf(TEXT("STATE: %s"), *Health.Status),
        StatusColor(Health.Status), PanelX + 16.0f, 48.0f, Font, 0.95f);
    if (bHasIntruder)
    {
        const float Range = Intruder.PositionEnuMetres.Length();
        const float Speed = Intruder.VelocityEnuMetresPerSecond.Length();
        DrawText(FString::Printf(TEXT("INTRUDER  %s"), *Intruder.Type.ToUpper()),
            Orange, PanelX + 16.0f, 76.0f, Font, 0.86f);
        DrawText(FString::Printf(TEXT("RNG %6.1f m   ALT %6.1f m"),
            Range, Intruder.PositionEnuMetres.Z),
            Body, PanelX + 16.0f, 96.0f, Font, 0.82f);
        DrawText(FString::Printf(TEXT("SPD %6.1f m/s  HDG %05.1f deg"),
            Speed, Intruder.HeadingDegrees),
            Body, PanelX + 16.0f, 114.0f, Font, 0.82f);
    }
    if (bHasInterceptor && bHasIntruder)
    {
        const float Separation = FVector::Distance(
            Intruder.PositionEnuMetres, Interceptor.PositionEnuMetres);
        const FVector Direction =
            (Intruder.PositionEnuMetres - Interceptor.PositionEnuMetres).GetSafeNormal();
        const float Closing = -FVector::DotProduct(
            Intruder.VelocityEnuMetresPerSecond
                - Interceptor.VelocityEnuMetresPerSecond,
            Direction);
        const float TimeToIntercept = Closing > 0.25f
            ? Separation / Closing : -1.0f;
        const float AltitudeDelta = Interceptor.PositionEnuMetres.Z
            - Intruder.PositionEnuMetres.Z;
        DrawText(TEXT("INTERCEPTOR  ACTIVE"), Blue,
            PanelX + 16.0f, 140.0f, Font, 0.86f);
        DrawText(FString::Printf(TEXT("SEP %6.1f m   CLOSING %6.1f m/s"),
            Separation, Closing),
            Body, PanelX + 16.0f, 160.0f, Font, 0.78f);
        DrawText(FString::Printf(TEXT("TTI %s   ALT DELTA %+6.1f m"),
            TimeToIntercept >= 0.0f
                ? *FString::Printf(TEXT("%4.1f s"), TimeToIntercept)
                : TEXT("---"),
            AltitudeDelta),
            Muted, PanelX + 16.0f, 177.0f, Font, 0.71f);
    }
    else
    {
        DrawText(TEXT("INTERCEPTOR  NOT DEPLOYED"), Muted,
            PanelX + 16.0f, 140.0f, Font, 0.86f);
    }

    const FLinearColor RadarColor =
        Health.bRadarFailure ? FLinearColor::Red : (Health.bRadarLocked ? Cyan : Muted);
    const FLinearColor EoColor =
        Health.bEoFailure ? FLinearColor::Red : (Health.bEoLocked ? Cyan : Muted);
    const FLinearColor ActColor =
        Health.bActuatorFailure ? FLinearColor::Red : FLinearColor(0.30f, 0.90f, 0.50f);
    DrawText(FString::Printf(TEXT("RADAR %-6s  EO %-6s  ACT %s"),
        *SensorState(Health.bRadarFailure, Health.bRadarLocked),
        *SensorState(Health.bEoFailure, Health.bEoLocked),
        Health.bActuatorFailure ? TEXT("FAILED") : TEXT("NOMINAL")),
        Body, PanelX + 16.0f, 190.0f, Font, 0.76f);
    DrawRect(RadarColor, PanelX + 16.0f, 210.0f, 104.0f, 3.0f);
    DrawRect(EoColor, PanelX + 128.0f, 210.0f, 104.0f, 3.0f);
    DrawRect(ActColor, PanelX + 240.0f, 210.0f, 104.0f, 3.0f);
    DrawText(FString::Printf(TEXT("FUSION: %s"), *Health.FusionSource.ToUpper()),
        Cyan, PanelX + 16.0f, 222.0f, Font, 0.72f);
    DrawText(FString::Printf(TEXT("SIM %.0fx REQUESTED  |  %.2fx ACHIEVED"),
        Health.RequestedSimulationRate, Health.AchievedRealtimeFactor),
        FLinearColor(0.56f, 0.82f, 0.95f, 1.0f),
        PanelX + 16.0f, 244.0f, Font, 0.76f);
    DrawText(FString::Printf(TEXT("GUIDANCE %s  |  N' %.2f"),
        *Health.GuidanceMode.ToUpper(),
        Health.GuidanceNavigationGain),
        Cyan, PanelX + 16.0f, 264.0f, Font, 0.72f);
    DrawText(FString::Printf(TEXT("CMD %.1f m/s  CLOSE %.1f  LOS %.2f deg/s"),
        Health.GuidanceCommandSpeedMps,
        Health.GuidanceClosingSpeedMps,
        Health.GuidanceLosRateDps),
        Body, PanelX + 16.0f, 284.0f, Font, 0.69f);
    DrawText(FString::Printf(TEXT("TRACK %.0f%%  |  AI RESIDUAL %.0f%%  |  CAP %.0f m/s"),
        Health.GuidanceTrackConfidence * 100.0,
        Health.AiResidualAuthority * 100.0,
        Health.InterceptorSpeedCapMps),
        Muted, PanelX + 16.0f, 304.0f, Font, 0.66f);
    DrawText(TEXT("SOURCE: AUTHORITATIVE PYTHON PHYSICS"),
        FLinearColor(0.38f, 0.76f, 0.74f, 0.85f),
        PanelX + 16.0f, 328.0f, Font, 0.70f);
    DrawText(TEXT("NO HARDWARE / WEAPON COMMAND PATH"),
        Muted, PanelX + 16.0f, 348.0f, Font, 0.66f);

    const float ControlY = ScreenH - 68.0f;
    const float RadarSize = 250.0f;
    const float RadarX = 16.0f;
    const float RadarY = ControlY - RadarSize - 12.0f;
    DrawRect(Panel, RadarX, RadarY, RadarSize, RadarSize);
    DrawRect(Cyan, RadarX, RadarY, RadarSize, 2.0f);
    DrawText(TEXT("LOCAL ENU RADAR PICTURE"), HeaderColor,
        RadarX + 12.0f, RadarY + 10.0f, Font, 0.78f);
    const FVector2D RadarCenter(RadarX + RadarSize * 0.5f, RadarY + RadarSize * 0.55f);
    const float RadarRadius = RadarSize * 0.39f;
    const float RadarRange = bHasIntruder
        ? FMath::Clamp(FMath::CeilToFloat(
            Intruder.PositionEnuMetres.Length() / 250.0f) * 250.0f,
            750.0f, 2000.0f)
        : 1000.0f;
    auto DrawCircleLines = [this](const FVector2D& Center, const float Radius,
        const FLinearColor& Color, const float Thickness)
    {
        constexpr int32 Segments = 48;
        for (int32 Index = 0; Index < Segments; ++Index)
        {
            const float A0 = 2.0f * PI * Index / Segments;
            const float A1 = 2.0f * PI * (Index + 1) / Segments;
            DrawLine(
                Center.X + FMath::Cos(A0) * Radius,
                Center.Y + FMath::Sin(A0) * Radius,
                Center.X + FMath::Cos(A1) * Radius,
                Center.Y + FMath::Sin(A1) * Radius,
                Color, Thickness);
        }
    };
    for (int32 Ring = 1; Ring <= 4; ++Ring)
    {
        DrawCircleLines(RadarCenter, RadarRadius * Ring / 4.0f,
            FLinearColor(0.20f, 0.46f, 0.50f, 0.45f), 1.0f);
    }
    DrawLine(RadarCenter.X - RadarRadius, RadarCenter.Y,
        RadarCenter.X + RadarRadius, RadarCenter.Y,
        FLinearColor(0.18f, 0.42f, 0.46f, 0.45f), 1.0f);
    DrawLine(RadarCenter.X, RadarCenter.Y - RadarRadius,
        RadarCenter.X, RadarCenter.Y + RadarRadius,
        FLinearColor(0.18f, 0.42f, 0.46f, 0.45f), 1.0f);
    const float SweepAngle = WorldSeconds * 0.85f;
    DrawLine(RadarCenter.X, RadarCenter.Y,
        RadarCenter.X + FMath::Cos(SweepAngle) * RadarRadius,
        RadarCenter.Y + FMath::Sin(SweepAngle) * RadarRadius,
        FLinearColor(0.12f, 0.95f, 0.62f, 0.70f), 2.0f);
    DrawRect(Cyan, RadarCenter.X - 3.0f, RadarCenter.Y - 3.0f, 6.0f, 6.0f);
    auto RadarPoint = [RadarCenter, RadarRadius, RadarRange](const FVector& Position)
    {
        return FVector2D(
            RadarCenter.X + Position.X / RadarRange * RadarRadius,
            RadarCenter.Y - Position.Y / RadarRange * RadarRadius);
    };
    if (bHasIntruder)
    {
        const FVector2D Point = RadarPoint(Intruder.PositionEnuMetres);
        DrawRect(Orange, Point.X - 5.0f, Point.Y - 5.0f, 10.0f, 10.0f);
    }
    if (bHasInterceptor)
    {
        const FVector2D Point = RadarPoint(Interceptor.PositionEnuMetres);
        DrawRect(Blue, Point.X - 4.0f, Point.Y - 4.0f, 8.0f, 8.0f);
    }
    if (Health.bHasPredictedIntercept)
    {
        const FVector2D Point = RadarPoint(Health.PredictedInterceptEnuMetres);
        DrawLine(Point.X - 6.0f, Point.Y, Point.X + 6.0f, Point.Y,
            FLinearColor::Yellow, 2.0f);
        DrawLine(Point.X, Point.Y - 6.0f, Point.X, Point.Y + 6.0f,
            FLinearColor::Yellow, 2.0f);
    }
    DrawText(FString::Printf(TEXT("RANGE %.0f m  |  N UP"), RadarRange),
        Muted, RadarX + 12.0f, RadarY + RadarSize - 22.0f, Font, 0.66f);

    const float GraphX = RadarX + RadarSize + 14.0f;
    const float GraphY = ControlY - 178.0f;
    const float GraphW = FMath::Max(320.0f, PanelX - GraphX - 14.0f);
    const float GraphH = 166.0f;
    DrawRect(Panel, GraphX, GraphY, GraphW, GraphH);
    DrawRect(Cyan, GraphX, GraphY, GraphW, 2.0f);
    DrawText(TEXT("LIVE FLIGHT HISTORY  |  SPEED / ALTITUDE / RANGE"),
        HeaderColor, GraphX + 12.0f, GraphY + 10.0f, Font, 0.74f);
    const float PlotX = GraphX + 12.0f;
    const float PlotY = GraphY + 38.0f;
    const float PlotW = GraphW - 24.0f;
    const float PlotH = GraphH - 58.0f;
    for (int32 Grid = 0; Grid <= 4; ++Grid)
    {
        const float Y = PlotY + PlotH * Grid / 4.0f;
        DrawLine(PlotX, Y, PlotX + PlotW, Y,
            FLinearColor(0.22f, 0.34f, 0.40f, 0.55f), 1.0f);
    }
    const float SpeedMax = FMath::Max(80.0f,
        static_cast<float>(Health.InterceptorSpeedCapMps) * 1.15f);
    const float RangeMaxGraph = 1200.0f;
    auto DrawSeries = [this, PlotX, PlotY, PlotW, PlotH](
        const TArray<float>& Samples, const float MaxValue,
        const FLinearColor& Color)
    {
        if (Samples.Num() < 2 || MaxValue <= 0.0f)
        {
            return;
        }
        for (int32 Index = 1; Index < Samples.Num(); ++Index)
        {
            const float X0 = PlotX + PlotW * (Index - 1) / (Samples.Num() - 1);
            const float X1 = PlotX + PlotW * Index / (Samples.Num() - 1);
            const float Y0 = PlotY + PlotH * (
                1.0f - FMath::Clamp(Samples[Index - 1] / MaxValue, 0.0f, 1.0f));
            const float Y1 = PlotY + PlotH * (
                1.0f - FMath::Clamp(Samples[Index] / MaxValue, 0.0f, 1.0f));
            DrawLine(X0, Y0, X1, Y1, Color, 1.8f);
        }
    };
    DrawSeries(IntruderSpeedHistory, SpeedMax, Orange);
    DrawSeries(InterceptorSpeedHistory, SpeedMax, Blue);
    DrawSeries(AltitudeHistory, 350.0f, FLinearColor::Yellow);
    DrawSeries(RangeHistory, RangeMaxGraph, FLinearColor(0.55f, 0.95f, 0.72f, 1.0f));
    DrawText(TEXT("INTRUDER SPD"), Orange,
        PlotX, GraphY + GraphH - 17.0f, Font, 0.62f);
    DrawText(TEXT("INTERCEPTOR SPD"), Blue,
        PlotX + 90.0f, GraphY + GraphH - 17.0f, Font, 0.62f);
    DrawText(TEXT("ALT"), FLinearColor::Yellow,
        PlotX + 210.0f, GraphY + GraphH - 17.0f, Font, 0.62f);
    DrawText(TEXT("RANGE"), FLinearColor(0.55f, 0.95f, 0.72f, 1.0f),
        PlotX + 250.0f, GraphY + GraphH - 17.0f, Font, 0.62f);

    DrawRect(FLinearColor(0.005f, 0.018f, 0.035f, 0.90f),
        16.0f, ControlY, ScreenW - 32.0f, 54.0f);
    DrawText(TEXT("[SPACE] PAUSE  [R] RESTART  [1/2/4/8] RATE  [C] CAMERA  [N] NEXT SCENARIO"),
        HeaderColor, 28.0f, ControlY + 7.0f, Font, 0.70f);
    DrawText(TEXT("[F5] RADAR FAIL  [F6] EO FAIL  [F7] ACTUATOR FAIL  [X] CLEAR FAILURES"),
        FLinearColor(0.92f, 0.72f, 0.38f, 1.0f),
        28.0f, ControlY + 27.0f, Font, 0.68f);
    if (const AAegisTacticalPlayerController* Controller =
        Cast<AAegisTacticalPlayerController>(GetOwningPlayerController()))
    {
        DrawText(Controller->GetLastLocalCommand(),
            FLinearColor(0.38f, 0.90f, 0.64f, 1.0f),
            ScreenW * 0.58f, ControlY + 27.0f, Font, 0.67f);
    }
}
