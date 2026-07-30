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
};
