#include "AegisTacticalHUD.h"

#include "AegisTacticalTelemetryManager.h"
#include "AegisTacticalCameraActor.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Kismet/GameplayStatics.h"
#include "TacticalTelemetryComponent.h"

namespace
{
FLinearColor StatusColor(const FString& Status)
{
    if (Status.Equals(TEXT("BREACH"), ESearchCase::IgnoreCase)) return FLinearColor(1.0f, 0.18f, 0.16f, 1.0f);
    if (Status.Equals(TEXT("INTERCEPTED"), ESearchCase::IgnoreCase)) return FLinearColor(0.22f, 0.95f, 0.48f, 1.0f);
    if (Status.Equals(TEXT("TRACKING"), ESearchCase::IgnoreCase)) return FLinearColor(1.0f, 0.73f, 0.18f, 1.0f);
    return FLinearColor(0.48f, 0.82f, 0.94f, 1.0f);
}
}

void AAegisTacticalHUD::DrawHUD()
{
    Super::DrawHUD();

    UFont* Font = GEngine != nullptr ? GEngine->GetSmallFont() : nullptr;
    DrawRect(FLinearColor(0.005f, 0.018f, 0.035f, 0.78f), 16.0f, 14.0f, 500.0f, 190.0f);
    DrawRect(FLinearColor(0.10f, 0.74f, 0.68f, 0.92f), 16.0f, 14.0f, 500.0f, 2.0f);
    const FLinearColor HeaderColor(0.70f, 0.88f, 1.0f, 1.0f);
    DrawText(TEXT("AEGIS TACTICAL VIEWER"), HeaderColor, 28.0f, 24.0f, Font, 1.35f);
    DrawText(TEXT("DISPLAY CLIENT  |  LOCAL UDP :8788  |  NO COMMAND PATH"),
        FLinearColor(0.68f, 0.72f, 0.76f, 1.0f), 28.0f, 50.0f, Font, 0.85f);
    const AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(
        GetOwningPlayerController() != nullptr ? GetOwningPlayerController()->GetViewTarget() : nullptr);
    DrawText(FString::Printf(TEXT("VIEW: %s  |  [C] CYCLE CAMERA"),
        Camera != nullptr ? *Camera->GetPresentationModeLabel() : TEXT("INITIALIZING")),
        FLinearColor(0.68f, 0.72f, 0.76f, 1.0f), 28.0f, 68.0f, Font, 0.78f);

    const AAegisTacticalTelemetryManager* Manager = Cast<AAegisTacticalTelemetryManager>(
        UGameplayStatics::GetActorOfClass(GetWorld(), AAegisTacticalTelemetryManager::StaticClass()));
    const UTacticalTelemetryComponent* Telemetry = Manager != nullptr ? Manager->Telemetry : nullptr;
    if (Telemetry == nullptr)
    {
        DrawText(TEXT("LINK: INITIALIZING"), FLinearColor::Yellow, 28.0f, 98.0f, Font, 1.1f);
        return;
    }

    const FTacticalTelemetryHealth& Health = Telemetry->GetHealth();
    const float WorldSeconds = GetWorld() != nullptr ? GetWorld()->GetTimeSeconds() : 0.0f;
    const bool bStale = Health.IsStale(WorldSeconds);
    const FLinearColor LinkColor = Health.ReceivedPackets == 0
        ? FLinearColor::Yellow
        : (bStale ? FLinearColor(1.0f, 0.55f, 0.10f, 1.0f) : FLinearColor(0.20f, 0.95f, 0.48f, 1.0f));
    const FString Link = Health.ReceivedPackets == 0
        ? TEXT("LINK: WAITING FOR LOCAL TELEMETRY")
        : FString::Printf(TEXT("LINK: %s  |  AGE: %.2fs  |  LOSS: %lld  |  REJECTED: %lld"),
            bStale ? TEXT("STALE") : TEXT("LIVE"), Health.PacketAgeSeconds(WorldSeconds),
            Health.DroppedPackets, Health.RejectedPackets);
    DrawText(Link, LinkColor, 28.0f, 98.0f, Font, 1.05f);

    DrawText(FString::Printf(TEXT("MISSION TIME: %.1fs  |  SEQUENCE: %lld  |  STATUS: %s"),
        Health.LastMissionTimeSeconds, Health.LastSequence, *Health.Status),
        FLinearColor(0.82f, 0.86f, 0.90f, 1.0f), 28.0f, 124.0f, Font, 0.92f);
    if (!Health.Site.IsEmpty())
    {
        DrawText(FString::Printf(TEXT("SITE: %s"), *Health.Site),
            FLinearColor(0.70f, 0.74f, 0.78f, 1.0f), 28.0f, 146.0f, Font, 0.88f);
    }
    DrawText(TEXT("SIMULATED TRAINING ENVIRONMENT"), FLinearColor(0.38f, 0.76f, 0.74f, 0.85f),
        28.0f, 164.0f, Font, 0.76f);

    FTacticalTrackSnapshot Intruder;
    FTacticalTrackSnapshot Interceptor;
    const bool bHasIntruder = Telemetry->GetLatestSnapshot(TEXT("intruder"), Intruder);
    const bool bHasInterceptor = Telemetry->GetLatestSnapshot(TEXT("interceptor"), Interceptor);
    const float PanelX = Canvas != nullptr ? Canvas->SizeX - 376.0f : 1500.0f;
    DrawRect(FLinearColor(0.005f, 0.018f, 0.035f, 0.78f), PanelX, 14.0f, 360.0f, 204.0f);
    DrawRect(StatusColor(Health.Status), PanelX, 14.0f, 360.0f, 2.0f);
    DrawText(TEXT("LIVE TACTICAL DATA"), HeaderColor, PanelX + 16.0f, 24.0f, Font, 1.05f);
    DrawText(FString::Printf(TEXT("STATE: %s"), *Health.Status), StatusColor(Health.Status),
        PanelX + 16.0f, 48.0f, Font, 0.95f);
    if (bHasIntruder)
    {
        const float Range = Intruder.PositionEnuMetres.Length();
        const float Speed = Intruder.VelocityEnuMetresPerSecond.Length();
        DrawText(FString::Printf(TEXT("INTRUDER  %s"), *Intruder.Type.ToUpper()), FLinearColor(1.0f, 0.58f, 0.36f, 1.0f),
            PanelX + 16.0f, 76.0f, Font, 0.86f);
        DrawText(FString::Printf(TEXT("RANGE  %6.1f m   ALT  %6.1f m"), Range, Intruder.PositionEnuMetres.Z),
            FLinearColor(0.82f, 0.86f, 0.90f, 1.0f), PanelX + 16.0f, 96.0f, Font, 0.82f);
        DrawText(FString::Printf(TEXT("SPEED  %6.1f m/s  HDG  %05.1f°"), Speed, Intruder.HeadingDegrees),
            FLinearColor(0.82f, 0.86f, 0.90f, 1.0f), PanelX + 16.0f, 114.0f, Font, 0.82f);
    }
    if (bHasInterceptor)
    {
        const float Separation = FVector::Distance(Intruder.PositionEnuMetres, Interceptor.PositionEnuMetres);
        const FVector Direction = (Intruder.PositionEnuMetres - Interceptor.PositionEnuMetres).GetSafeNormal();
        const float Closing = -FVector::DotProduct(Intruder.VelocityEnuMetresPerSecond - Interceptor.VelocityEnuMetresPerSecond, Direction);
        DrawText(TEXT("INTERCEPTOR  ACTIVE"), FLinearColor(0.30f, 0.75f, 1.0f, 1.0f),
            PanelX + 16.0f, 144.0f, Font, 0.86f);
        DrawText(FString::Printf(TEXT("SEPARATION  %6.1f m  CLOSING  %6.1f m/s"), Separation, Closing),
            FLinearColor(0.82f, 0.86f, 0.90f, 1.0f), PanelX + 16.0f, 164.0f, Font, 0.78f);
    }
    else
    {
        DrawText(TEXT("INTERCEPTOR  NOT DEPLOYED"), FLinearColor(0.60f, 0.65f, 0.70f, 1.0f),
            PanelX + 16.0f, 144.0f, Font, 0.86f);
    }
    DrawText(TEXT("SOURCE: VALIDATED PYTHON TELEMETRY"), FLinearColor(0.38f, 0.76f, 0.74f, 0.85f),
        PanelX + 16.0f, 190.0f, Font, 0.70f);
}
