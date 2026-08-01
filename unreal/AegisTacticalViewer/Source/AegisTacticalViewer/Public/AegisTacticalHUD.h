#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "AegisTacticalHUD.generated.h"

/** Read-only on-screen status for the local presentation client. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalHUD : public AHUD
{
    GENERATED_BODY()

public:
    virtual void DrawHUD() override;

    void DrawCornerBracket(float X, float Y, float DirX, float DirY, float Size, const FLinearColor& Color, float Thickness = 1.7f);

    void DrawThreatAssessmentPanel(
        float X, float Y, 
        const struct FTacticalTrackSnapshot* Intruder,
        float MissionTimeSeconds,
        const FLinearColor& PanelColor,
        const FLinearColor& HeaderColor,
        const FLinearColor& BodyColor,
        const FLinearColor& MutedColor,
        const FLinearColor& CyanColor,
        const FLinearColor& OrangeColor,
        class UFont* Font);

    void TogglePresentationMode() { bCleanCinematicMode = !bCleanCinematicMode; }
    bool IsCleanCinematicMode() const { return bCleanCinematicMode; }

private:
    void UpdateHistory(
        const struct FTacticalTelemetryHealth& Health,
        const struct FTacticalTrackSnapshot* Intruder,
        const struct FTacticalTrackSnapshot* Interceptor);

    TArray<float> IntruderSpeedHistory;
    TArray<float> InterceptorSpeedHistory;
    TArray<float> AltitudeHistory;
    TArray<float> RangeHistory;
    double LastHistoryMissionTime = -1.0;
    // The default is deliberately unobstructed: a flight replay must show
    // world-space motion before it shows instrumentation. H restores the
    // complete tactical overlay at any time.
    bool bCleanCinematicMode = true;
};
